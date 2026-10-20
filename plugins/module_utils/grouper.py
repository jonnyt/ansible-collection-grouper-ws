# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Shared client for the Grouper Web Services REST API."""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import re
from html import unescape

from ansible.module_utils.basic import env_fallback, missing_required_lib
from ansible.module_utils.common.text.converters import to_native, to_text
from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils.urls import open_url
from ansible_collections.grouper.ws.plugins.module_utils.grouper_jwt import (
    HAS_CRYPTOGRAPHY,
    GrouperJwtError,
    bearer_token,
    load_private_key,
)

#: Argument spec shared by every module in this collection.
GROUPER_ARG_SPEC = dict(
    ws_url=dict(type='str', required=True,
                fallback=(env_fallback, ['GROUPER_WS_URL'])),
    api_version=dict(type='str', default='v6_0_000',
                     fallback=(env_fallback, ['GROUPER_WS_API_VERSION'])),
    username=dict(type='str',
                  fallback=(env_fallback, ['GROUPER_WS_USERNAME'])),
    password=dict(type='str', no_log=True,
                  fallback=(env_fallback, ['GROUPER_WS_PASSWORD'])),
    token=dict(type='str', no_log=True,
               fallback=(env_fallback, ['GROUPER_WS_TOKEN'])),
    jwt_prefix=dict(type='str',
                    fallback=(env_fallback, ['GROUPER_WS_JWT_PREFIX'])),
    jwt_private_key=dict(type='str', no_log=True,
                         fallback=(env_fallback, ['GROUPER_WS_JWT_PRIVATE_KEY'])),
    jwt_private_key_path=dict(
        type='path',
        fallback=(env_fallback, ['GROUPER_WS_JWT_PRIVATE_KEY_PATH'])),
    jwt_claims=dict(type='dict'),
    jwt_lifetime=dict(type='int'),
    act_as_subject_id=dict(type='str'),
    act_as_subject_identifier=dict(type='str'),
    act_as_subject_source_id=dict(type='str'),
    validate_certs=dict(type='bool', default=True),
    ca_path=dict(type='path'),
    timeout=dict(type='int', default=60),
)

GROUPER_MUTUALLY_EXCLUSIVE = [
    ('password', 'token'),
    ('username', 'token'),
    ('act_as_subject_id', 'act_as_subject_identifier'),
    ('jwt_private_key', 'jwt_private_key_path'),
    ('token', 'jwt_private_key'),
    ('token', 'jwt_private_key_path'),
    ('password', 'jwt_private_key'),
    ('password', 'jwt_private_key_path'),
    ('username', 'jwt_private_key'),
    ('username', 'jwt_private_key_path'),
]

GROUPER_REQUIRED_TOGETHER = [
    ('username', 'password'),
]

GROUPER_REQUIRED_ONE_OF = [
    ('password', 'token', 'jwt_private_key', 'jwt_private_key_path'),
]

#: How Grouper reports a jwt_prefix whose member id resolves to nothing. The
#: first comes from MemberFinder, the second from the password lookup after it.
UNKNOWN_JWT_MEMBER_MARKERS = ('MemberNotFoundException', "find public key")

#: A private key is useless without the prefix naming the entity it belongs to.
GROUPER_REQUIRED_BY = {
    'jwt_private_key': ('jwt_prefix',),
    'jwt_private_key_path': ('jwt_prefix',),
}


def grouper_argument_spec(**extra):
    """Return the common arg spec merged with module specific arguments."""
    spec = dict(GROUPER_ARG_SPEC)
    spec.update(extra)
    return spec


def is_true(value):
    """Grouper renders booleans as the strings 'T' and 'F'."""
    return to_text(value, errors='surrogate_or_strict').upper() == 'T'


def to_ws_bool(value):
    return 'T' if value else 'F'


def _per_item_failures(envelope):
    """Return readable reasons from any per-item results that did not succeed."""
    details = []
    for value in envelope.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            meta = item.get('resultMetadata')
            if not isinstance(meta, dict) or is_true(meta.get('success', 'F')):
                continue
            code = meta.get('resultCode')
            text = _condense_stack_trace(meta.get('resultMessage'))
            if code and text:
                details.append('%s: %s' % (code, text))
            elif code or text:
                details.append(code or text)
    return details


def _condense_stack_trace(text):
    """Keep the useful lines of a Java exception and drop the frames.

    Grouper returns whole stack traces as the result message, and the line
    that actually says what went wrong is the last 'Caused by', hundreds of
    frames down. Truncating from the front would discard it.
    """
    if not text:
        return text
    lines = [line.strip() for line in text.strip().splitlines()]
    kept = [line for line in lines
            if line and not line.startswith('at ') and not line.startswith('... ')]
    if not kept:
        return text.strip()[:500]
    # The first line states the failure, each 'Caused by' narrows it.
    summary = [kept[0]] + [line for line in kept[1:] if line.startswith('Caused by:')]
    return ' / '.join(summary)[:1000]


def summarise_body(raw):
    """Reduce an error body to something readable in a task failure message.

    Grouper sits behind Tomcat, which answers auth and routing failures with a
    full HTML error page. Dumping that verbatim buries the actual reason, so
    strip the markup and keep the first meaningful line.
    """
    text = to_native(raw, errors='surrogate_or_replace')
    if '<html' in text.lower() or '<!doctype' in text.lower():
        text = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', text)
        text = re.sub(r'(?s)<[^>]+>', ' ', text)
        text = unescape(text)
    text = ' '.join(text.split())
    return text[:500] if text else '(empty response body)'


class GrouperError(Exception):
    """Raised when Grouper reports a failure or the transport breaks."""

    def __init__(self, message, status=None, body=None):
        super(GrouperError, self).__init__(message)
        self.message = message
        self.status = status
        self.body = body


class GrouperClient(object):
    """Thin JSON REST client for grouper-ws.

    Every Grouper REST call in this collection is a POST of a single
    ``{"WsRest<Something>Request": {...}}`` envelope to a resource path, and
    every response is a single ``{"Ws<Something>Results": {...}}`` envelope.
    :meth:`post` handles wrapping, unwrapping and result checking so the
    modules only deal with the inner payloads.
    """

    def __init__(self, module):
        self.module = module
        params = module.params

        self.ws_url = params['ws_url'].rstrip('/')
        self.api_version = params['api_version']
        self.timeout = params['timeout']
        self.validate_certs = params['validate_certs']
        self.ca_path = params['ca_path']

        self.username = params.get('username')
        self.password = params.get('password')
        self.token = params.get('token')

        self.jwt_prefix = params.get('jwt_prefix')
        self.jwt_claims = params.get('jwt_claims')
        self.jwt_lifetime = params.get('jwt_lifetime')
        self.jwt_key = self._load_jwt_key(params)

        self.act_as = self._build_act_as(params)

    @staticmethod
    def _load_jwt_key(params):
        """Read and parse the JWT private key once, so a bad key fails fast.

        Parsing here rather than at the first request means an unreadable file
        or a mangled key is reported before any state is touched.
        """
        material = params.get('jwt_private_key')
        path = params.get('jwt_private_key_path')
        if not material and not path:
            return None

        if not HAS_CRYPTOGRAPHY:
            raise GrouperError(missing_required_lib('cryptography'))

        if path:
            try:
                with open(path, 'rb') as handle:
                    material = handle.read()
            except (IOError, OSError) as exc:
                raise GrouperError(
                    'Could not read jwt_private_key_path %s: %s'
                    % (path, to_native(exc)))

        try:
            return load_private_key(material)
        except GrouperJwtError as exc:
            raise GrouperError(to_native(exc))

    def _jwt_authorization(self):
        """Mint a fresh JWT for a single request.

        Grouper rejects a JWT whose iat is older than
        grouper.selfService.jwt.maxValidTimeInSeconds (600 by default), and a
        module run makes several calls, so tokens are never reused.
        """
        try:
            return bearer_token(self.jwt_prefix, self.jwt_key,
                                self.jwt_claims, self.jwt_lifetime)
        except GrouperJwtError as exc:
            raise GrouperError(to_native(exc))

    @staticmethod
    def _build_act_as(params):
        act_as = {}
        if params.get('act_as_subject_id'):
            act_as['subjectId'] = params['act_as_subject_id']
        if params.get('act_as_subject_identifier'):
            act_as['subjectIdentifier'] = params['act_as_subject_identifier']
        if params.get('act_as_subject_source_id'):
            act_as['subjectSourceId'] = params['act_as_subject_source_id']
        return act_as or None

    def endpoint(self, resource):
        return '%s/servicesRest/%s/%s' % (self.ws_url, self.api_version, resource)

    def post(self, resource, request_name, body):
        """POST a request envelope and return the unwrapped result payload.

        :param resource: REST resource, e.g. ``stems``.
        :param request_name: envelope key, e.g. ``WsRestStemSaveRequest``.
        :param body: the request object placed inside the envelope.
        :raises GrouperError: on transport failure or a Grouper failure result.
        """
        if self.act_as and 'actAsSubjectLookup' not in body:
            body = dict(body, actAsSubjectLookup=self.act_as)

        url = self.endpoint(resource)
        payload = json.dumps({request_name: body})

        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'Accept': 'application/json',
        }
        kwargs = dict(
            method='POST',
            data=payload,
            headers=headers,
            timeout=self.timeout,
            validate_certs=self.validate_certs,
            follow_redirects='none',
        )
        if self.ca_path:
            kwargs['ca_path'] = self.ca_path
        if self.jwt_key:
            headers['Authorization'] = 'Bearer %s' % self._jwt_authorization()
        elif self.token:
            headers['Authorization'] = 'Bearer %s' % self.token
        else:
            kwargs['url_username'] = self.username
            kwargs['url_password'] = self.password
            kwargs['force_basic_auth'] = True

        try:
            response = open_url(url, **kwargs)
            raw = response.read()
            status = response.getcode()
        except HTTPError as exc:
            raw = exc.read()
            status = exc.code
            self._raise_for_body(url, status, raw)
            # _raise_for_body always raises for a non-2xx status.
            raise
        except URLError as exc:
            raise GrouperError(
                'Could not reach Grouper at %s: %s' % (url, to_native(exc.reason)))
        except Exception as exc:  # pragma: no cover - defensive
            raise GrouperError(
                'Request to %s failed: %s' % (url, to_native(exc)))

        return self._parse(url, status, raw)

    def _auth_hint(self):
        """Explain a 401 in terms of the authentication actually in use.

        A rejected JWT looks exactly like a wrong password, but the usual
        causes are quite different, and Grouper's own response says nothing.
        """
        if self.jwt_key:
            return ('Check that jwt_prefix names the entity owning this private '
                    'key, that the clock here is within '
                    'grouper.selfService.jwt.maxValidTimeInSeconds of the '
                    'server, and that the entity is a member of any group named '
                    'by ws.client.user.group.name.')
        return ('Check the Grouper WS credentials and that the account is '
                'authorised for web services.')

    def _raise_for_body(self, url, status, raw):
        """Turn an HTTP error response into the most useful message available."""
        detail = None
        parsed = self._loads(raw)
        if isinstance(parsed, dict):
            detail = self._extract_message(parsed)
        if not detail:
            detail = summarise_body(raw)

        if status == 401:
            raise GrouperError(
                'Authentication to %s failed (HTTP 401). %s Server said: %s'
                % (url, self._auth_hint(), detail), status=status)

        # Grouper resolves the member id out of the prefix before it so much as
        # looks at the JWT, and a prefix naming no member throws rather than
        # returning null -- so the commonest JWT mistake of all arrives as a 500
        # with the reason buried in a stack trace.
        if self.jwt_key and any(marker in to_native(detail or '')
                                for marker in UNKNOWN_JWT_MEMBER_MARKERS):
            raise GrouperError(
                'Grouper could not find the entity named by jwt_prefix at %s '
                '(HTTP %s). That prefix encodes the entity\'s member id, so '
                'check it was copied whole from the entity page in the Grouper '
                'UI. Server said: %s' % (url, status, detail),
                status=status, body=detail)

        raise GrouperError(
            'Grouper returned HTTP %s for %s: %s' % (status, url, detail),
            status=status, body=detail)

    @staticmethod
    def _loads(raw):
        try:
            return json.loads(to_text(raw, errors='surrogate_or_strict'))
        except (ValueError, UnicodeError):
            return None

    @staticmethod
    def _extract_message(parsed):
        """Pull a human message out of a Grouper result or problem envelope.

        The outer resultMetadata on a batch failure only says how many items
        failed. The reason lives on the per-item result, so collect those too
        or the caller is left with "0 successes and 1 failures".
        """
        for envelope in parsed.values():
            if not isinstance(envelope, dict):
                continue
            meta = envelope.get('resultMetadata')
            if not isinstance(meta, dict):
                continue
            message = meta.get('resultMessage') or meta.get('resultCode')
            details = _per_item_failures(envelope)
            if details:
                return '%s [%s]' % (message, '; '.join(details))
            return message
        return None

    def _parse(self, url, status, raw):
        parsed = self._loads(raw)
        if parsed is None:
            raise GrouperError(
                'Grouper returned a non-JSON response (HTTP %s) from %s: %s'
                % (status, url,
                   to_native(raw, errors='surrogate_or_replace')[:2000]))

        if len(parsed) != 1:
            raise GrouperError(
                'Unexpected Grouper response envelope from %s: keys=%s'
                % (url, sorted(parsed.keys())))

        envelope_name, envelope = list(parsed.items())[0]

        if envelope_name == 'WsRestResultProblem':
            raise GrouperError(
                'Grouper rejected the request to %s: %s'
                % (url, self._extract_message(parsed) or envelope))

        meta = envelope.get('resultMetadata') or {}
        if not is_true(meta.get('success', 'F')):
            raise GrouperError(
                'Grouper call to %s failed (%s): %s'
                % (url, meta.get('resultCode'), meta.get('resultMessage')))

        return envelope


def result_code(result):
    """Return the resultCode of a per-item result block, or None."""
    if not isinstance(result, dict):
        return None
    return (result.get('resultMetadata') or {}).get('resultCode')


#: Per-item save result codes that mean Grouper actually wrote something.
CHANGED_RESULT_CODES = frozenset(['SUCCESS_INSERTED', 'SUCCESS_UPDATED'])
#: Per-item save result code meaning the object already matched the request.
UNCHANGED_RESULT_CODE = 'SUCCESS_NO_CHANGES_NEEDED'


def save_changed(result):
    """Map a stemSave/groupSave per-item result to an Ansible changed flag."""
    code = result_code(result)
    if code == UNCHANGED_RESULT_CODE:
        return False
    if code in CHANGED_RESULT_CODES:
        return True
    # Unknown but successful codes are treated as a change so we never under
    # report. Grouper only returns the three codes above for saves today.
    return True

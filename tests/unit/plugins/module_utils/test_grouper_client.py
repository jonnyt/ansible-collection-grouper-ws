# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json

import pytest

from ansible_collections.grouper.ws.plugins.module_utils.grouper import (
    GrouperClient,
    _condense_stack_trace,
    GrouperError,
    is_true,
    save_changed,
    summarise_body,
    to_ws_bool,
)


class FakeModule:
    """Just enough of AnsibleModule for GrouperClient's constructor."""

    def __init__(self, **overrides):
        self.params = {
            'ws_url': 'https://grouper.example.edu/grouper-ws/',
            'api_version': 'v2_6_000',
            'username': 'banderson',
            'password': 'secret',
            'token': None,
            'jwt_prefix': None,
            'jwt_private_key': None,
            'jwt_private_key_path': None,
            'jwt_claims': None,
            'jwt_lifetime': None,
            'act_as_subject_id': None,
            'act_as_subject_identifier': None,
            'act_as_subject_source_id': None,
            'validate_certs': True,
            'ca_path': None,
            'timeout': 60,
        }
        self.params.update(overrides)


def client(**overrides):
    return GrouperClient(FakeModule(**overrides))


@pytest.fixture(scope='module')
def rsa_key_pem():
    cryptography = pytest.importorskip('cryptography')  # noqa: F841
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def jwt_client(key_pem, **overrides):
    overrides.setdefault('username', None)
    overrides.setdefault('password', None)
    return client(jwt_prefix='jwtUser_YWMy=_', jwt_private_key=key_pem, **overrides)


class FakeResponse:
    """The parts of an http.client response that GrouperClient.post touches."""

    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def getcode(self):
        return 200


SUCCESS = {'WsStemSaveResults': {'resultMetadata': {'success': 'T'}}}


@pytest.fixture
def sent(mocker):
    """Capture the open_url kwargs of every request the client makes."""
    return mocker.patch(
        'ansible_collections.grouper.ws.plugins.module_utils.grouper.open_url',
        side_effect=lambda *args, **kwargs: FakeResponse(SUCCESS))


class TestAuthentication:
    """Which credential ends up on the wire, and in what shape."""

    def test_basic_auth_is_forced_rather_than_waiting_for_a_challenge(self, sent):
        client().post('stems', 'WsRestStemSaveRequest', {})
        kwargs = sent.call_args.kwargs
        assert kwargs['url_username'] == 'banderson'
        assert kwargs['url_password'] == 'secret'
        assert kwargs['force_basic_auth'] is True
        assert 'Authorization' not in kwargs['headers']

    def test_a_static_token_is_sent_verbatim(self, sent):
        client(username=None, password=None, token='abc123').post(
            'stems', 'WsRestStemSaveRequest', {})
        kwargs = sent.call_args.kwargs
        assert kwargs['headers']['Authorization'] == 'Bearer abc123'
        assert 'url_password' not in kwargs

    def test_jwt_takes_precedence_and_carries_no_basic_credentials(
            self, sent, rsa_key_pem):
        jwt_client(rsa_key_pem).post('stems', 'WsRestStemSaveRequest', {})
        kwargs = sent.call_args.kwargs
        assert kwargs['headers']['Authorization'].startswith('Bearer jwtUser_YWMy=_')
        assert 'url_password' not in kwargs
        assert 'force_basic_auth' not in kwargs

    def test_every_request_is_signed_afresh(self, sent, rsa_key_pem):
        """Grouper caps a JWT's age, so a run's later calls need new tokens."""
        jwt = jwt_client(rsa_key_pem)
        jwt.post('stems', 'WsRestStemSaveRequest', {})
        first = sent.call_args.kwargs['headers']['Authorization']
        jwt.post('stems', 'WsRestStemSaveRequest', {})
        second = sent.call_args.kwargs['headers']['Authorization']
        assert first != second

    def test_a_bad_key_fails_before_any_request_is_made(self, sent):
        with pytest.raises(GrouperError, match='Could not read'):
            jwt_client('-----BEGIN PRIVATE KEY-----\nnope\n-----END PRIVATE KEY-----')
        assert sent.call_count == 0

    def test_an_unreadable_key_file_names_the_path(self, sent):
        with pytest.raises(GrouperError, match='/nonexistent/grouper.key'):
            client(username=None, password=None, jwt_prefix='jwtUser_YWMy=_',
                   jwt_private_key_path='/nonexistent/grouper.key')
        assert sent.call_count == 0


class TestBooleanHelpers:

    @pytest.mark.parametrize('value,expected', [
        ('T', True), ('t', True), ('F', False), ('f', False), ('', False),
    ])
    def test_is_true(self, value, expected):
        assert is_true(value) is expected

    def test_to_ws_bool(self):
        assert to_ws_bool(True) == 'T'
        assert to_ws_bool(False) == 'F'


class TestEndpoint:

    def test_trailing_slash_on_ws_url_is_tolerated(self):
        assert client().endpoint('stems') == \
            'https://grouper.example.edu/grouper-ws/servicesRest/v2_6_000/stems'

    def test_api_version_is_used(self):
        assert client(api_version='v5_0_000').endpoint('groups').endswith(
            '/servicesRest/v5_0_000/groups')


class TestActAs:

    def test_absent_by_default(self):
        assert client().act_as is None

    def test_subject_id(self):
        assert client(act_as_subject_id='GrouperSystem').act_as == \
            {'subjectId': 'GrouperSystem'}

    def test_identifier_and_source(self):
        assert client(act_as_subject_identifier='banderson',
                      act_as_subject_source_id='ldap').act_as == \
            {'subjectIdentifier': 'banderson', 'subjectSourceId': 'ldap'}


class TestParse:

    def test_unwraps_the_single_envelope(self):
        raw = json.dumps({'WsStemSaveResults': {
            'resultMetadata': {'success': 'T', 'resultCode': 'SUCCESS'},
            'results': [{'wsStem': {'name': 'a:b'}}],
        }})
        envelope = client()._parse('u', 200, raw)
        assert envelope['results'][0]['wsStem']['name'] == 'a:b'

    def test_failure_result_raises(self):
        raw = json.dumps({'WsStemSaveResults': {
            'resultMetadata': {'success': 'F', 'resultCode': 'EXCEPTION',
                               'resultMessage': 'boom'},
        }})
        with pytest.raises(GrouperError) as excinfo:
            client()._parse('u', 200, raw)
        assert 'EXCEPTION' in str(excinfo.value)
        assert 'boom' in str(excinfo.value)

    def test_rest_result_problem_raises(self):
        raw = json.dumps({'WsRestResultProblem': {
            'resultMetadata': {'success': 'F',
                               'resultMessage': 'bad request shape'},
        }})
        with pytest.raises(GrouperError) as excinfo:
            client()._parse('u', 500, raw)
        assert 'bad request shape' in str(excinfo.value)

    def test_non_json_raises_with_a_readable_message(self):
        with pytest.raises(GrouperError) as excinfo:
            client()._parse('u', 500, '<html>Tomcat exploded</html>')
        assert 'non-JSON' in str(excinfo.value)
        assert 'Tomcat exploded' in str(excinfo.value)

    def test_unexpected_envelope_shape_raises(self):
        with pytest.raises(GrouperError) as excinfo:
            client()._parse('u', 200, json.dumps({'a': {}, 'b': {}}))
        assert 'Unexpected Grouper response envelope' in str(excinfo.value)


class TestRaiseForBody:

    def test_401_explains_the_likely_cause(self):
        with pytest.raises(GrouperError) as excinfo:
            client()._raise_for_body('u', 401, 'Unauthorized')
        assert excinfo.value.status == 401
        assert 'credentials' in str(excinfo.value)

    def test_401_under_jwt_points_at_the_jwt_failure_modes(self, rsa_key_pem):
        """A rejected JWT looks like a bad password but rarely is one."""
        with pytest.raises(GrouperError) as excinfo:
            jwt_client(rsa_key_pem)._raise_for_body('u', 401, 'Unauthorized')
        message = str(excinfo.value)
        assert 'jwt_prefix' in message
        assert 'maxValidTimeInSeconds' in message

    def test_a_prefix_naming_no_member_is_explained(self, rsa_key_pem):
        """The commonest JWT mistake arrives as a 500, not a 401.

        Grouper resolves the member id from the prefix before reading the JWT,
        and throws when it finds nothing, so the reason lands inside a Tomcat
        stack trace instead of an authentication failure.
        """
        raw = ('<html><body>HTTP Status 500 Exception '
               'edu.internet2.middleware.grouper.exception.'
               'MemberNotFoundException at Hib3MemberDAO.java:379</body></html>')
        with pytest.raises(GrouperError) as excinfo:
            jwt_client(rsa_key_pem)._raise_for_body('u', 500, raw)
        assert 'jwt_prefix' in str(excinfo.value)
        assert excinfo.value.status == 500

    def test_the_same_500_under_basic_auth_is_left_alone(self):
        raw = 'MemberNotFoundException somewhere unrelated'
        with pytest.raises(GrouperError) as excinfo:
            client()._raise_for_body('u', 500, raw)
        assert 'jwt_prefix' not in str(excinfo.value)

    def test_other_errors_surface_the_grouper_message(self):
        raw = json.dumps({'WsRestResultProblem': {
            'resultMetadata': {'resultMessage': 'stem not found'},
        }})
        with pytest.raises(GrouperError) as excinfo:
            client()._raise_for_body('u', 500, raw)
        assert 'stem not found' in str(excinfo.value)


class TestSaveChanged:
    """Grouper reports idempotency directly, so 'changed' comes from it."""

    def test_no_changes_needed_is_not_changed(self):
        assert save_changed(
            {'resultMetadata': {'resultCode': 'SUCCESS_NO_CHANGES_NEEDED'}}) is False

    @pytest.mark.parametrize('code', ['SUCCESS_INSERTED', 'SUCCESS_UPDATED'])
    def test_writes_are_changed(self, code):
        assert save_changed({'resultMetadata': {'resultCode': code}}) is True

    def test_unknown_codes_are_reported_as_changed(self):
        assert save_changed({'resultMetadata': {'resultCode': 'SOMETHING'}}) is True


class TestSummariseBody:
    """Tomcat answers auth failures with a full HTML page; keep it readable."""

    def test_html_is_stripped_to_its_text(self):
        html = ('<!doctype html><html><head><title>HTTP Status 401</title>'
                '<style type="text/css">body {font-family:Tahoma;}</style>'
                '</head><body><h1>HTTP Status 401 &ndash; Unauthorized</h1>'
                '<p><b>Message</b> Unauthorized</p></body></html>')
        summary = summarise_body(html)
        assert 'font-family' not in summary
        assert '<' not in summary
        assert 'HTTP Status 401' in summary
        assert 'Unauthorized' in summary

    def test_entities_are_decoded(self):
        assert '&ndash;' not in summarise_body('<html><p>a &ndash; b</p></html>')

    def test_plain_text_is_passed_through(self):
        assert summarise_body('something broke') == 'something broke'

    def test_whitespace_is_collapsed(self):
        assert summarise_body('a\n\n   b\t c') == 'a b c'

    def test_empty_body_is_described(self):
        assert summarise_body('') == '(empty response body)'

    def test_long_bodies_are_truncated(self):
        assert len(summarise_body('x' * 5000)) == 500


class TestPerItemFailureReporting:
    """A batch failure only says how many failed; the reason is per item."""

    def test_per_item_reason_is_surfaced(self):
        parsed = {'WsGroupSaveResults': {
            'resultMetadata': {'success': 'F',
                               'resultMessage': '0 successes and 1 failures'},
            'results': [{'resultMetadata': {
                'success': 'F', 'resultCode': 'EXCEPTION',
                'resultMessage': 'Group name must contain a stem name'}}],
        }}
        message = GrouperClient._extract_message(parsed)
        assert '0 successes and 1 failures' in message
        assert 'Group name must contain a stem name' in message
        assert 'EXCEPTION' in message

    def test_successful_items_are_not_reported_as_failures(self):
        parsed = {'WsGroupSaveResults': {
            'resultMetadata': {'success': 'F', 'resultMessage': 'partial'},
            'results': [
                {'resultMetadata': {'success': 'T',
                                    'resultCode': 'SUCCESS_INSERTED'}},
                {'resultMetadata': {'success': 'F', 'resultCode': 'BOOM'}},
            ],
        }}
        message = GrouperClient._extract_message(parsed)
        assert 'BOOM' in message
        assert 'SUCCESS_INSERTED' not in message

    def test_message_without_per_item_results_is_unchanged(self):
        parsed = {'WsRestResultProblem': {
            'resultMetadata': {'resultMessage': 'bad shape'},
        }}
        assert GrouperClient._extract_message(parsed) == 'bad shape'


class TestCondenseStackTrace:

    def test_frames_are_dropped_and_root_cause_kept(self):
        trace = (
            "java.lang.RuntimeException: outer failure\n"
            "\tat edu.internet2.middleware.grouper.Foo.save(Foo.java:429)\n"
            "\tat edu.internet2.middleware.grouper.Bar.run(Bar.java:12)\n"
            "Caused by: java.lang.RuntimeException: the real reason\n"
            "\tat edu.internet2.middleware.grouper.Baz.go(Baz.java:645)\n"
            "\t... 43 more")
        condensed = _condense_stack_trace(trace)
        assert 'outer failure' in condensed
        assert 'the real reason' in condensed
        assert 'Foo.java' not in condensed
        assert '43 more' not in condensed

    def test_plain_message_is_left_alone(self):
        assert _condense_stack_trace('just a message') == 'just a message'

    def test_none_is_passed_through(self):
        assert _condense_stack_trace(None) is None

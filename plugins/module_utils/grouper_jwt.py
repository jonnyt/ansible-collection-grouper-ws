# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Mint the signed bearer tokens Grouper's private key JWT authentication expects.

Grouper matches the whole Authorization header against
``^Bearer jwtUser_([^_]+)_(.*)$`` (``GrouperPublicPrivateKeyJwt.java``), so the
value is a site supplied prefix followed immediately by a freshly signed JWT.
The prefix identifies the entity; the JWT only proves possession of its key.

Only ``iat`` is required in the payload, and it must be no older than
``grouper.selfService.jwt.maxValidTimeInSeconds`` (600 by default), which is why
:func:`bearer_token` signs a new JWT per request instead of caching one.

Kept separate from ``grouper`` so the cryptography import stays optional: a
playbook using basic auth must not need it installed.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import binascii
import json
import time
import traceback
import uuid

from ansible.module_utils.common.text.converters import to_bytes, to_native

CRYPTOGRAPHY_IMPORT_ERROR = None
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    CRYPTOGRAPHY_IMPORT_ERROR = traceback.format_exc()

#: Present in every PEM encoding, absent from the bare base64 Grouper downloads.
PEM_MARKER = b'-----BEGIN'


class GrouperJwtError(Exception):
    """Raised when a JWT cannot be built from the supplied key or prefix."""


def _b64url(raw):
    """base64url with the padding stripped, as JWS requires."""
    return base64.urlsafe_b64encode(raw).rstrip(b'=')


def _segment(obj):
    return _b64url(to_bytes(json.dumps(obj, separators=(',', ':'), sort_keys=True)))


def load_private_key(material):
    """Load an RSA private key in any of the forms Grouper and OpenSSL produce.

    Grouper's UI downloads base64 PKCS#8 DER with no PEM header, even though the
    wiki tells you to add a PKCS#1 ``BEGIN RSA PRIVATE KEY`` header. Rather than
    guess which of those a site pasted, accept the bare form and both PEM
    wrappers; ``load_der_private_key`` already distinguishes PKCS#1 from PKCS#8.
    """
    if not HAS_CRYPTOGRAPHY:
        raise GrouperJwtError(
            'The cryptography library is required to sign Grouper JWTs.')

    data = to_bytes(material, errors='surrogate_or_strict').strip()
    if not data:
        raise GrouperJwtError('The JWT private key is empty.')

    try:
        if PEM_MARKER in data:
            key = serialization.load_pem_private_key(data, password=None)
        else:
            key = serialization.load_der_private_key(
                base64.b64decode(b''.join(data.split())), password=None)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise GrouperJwtError(
            'Could not read the JWT private key: %s. Supply it exactly as '
            'Grouper downloaded it, or as an unencrypted PEM file.'
            % to_native(exc))

    if not isinstance(key, RSAPrivateKey):
        raise GrouperJwtError(
            'Grouper JWT authentication needs an RSA private key, but the '
            'supplied key is %s.' % type(key).__name__)
    return key


def normalise_prefix(prefix):
    """Return the bearer prefix in the exact shape Grouper's regex expects.

    The UI shows the prefix with its trailing underscore, but it is routinely
    pasted with a leading ``Bearer`` or with the underscore trimmed off, and
    Grouper answers both with an unexplained 401.
    """
    text = to_native(prefix or '').strip()
    if text.lower().startswith('bearer '):
        text = text[len('bearer '):].strip()
    if not text:
        raise GrouperJwtError('The JWT prefix is empty.')
    return text if text.endswith('_') else text + '_'


def build_jwt(private_key, claims=None, lifetime=None):
    """Sign an RS256 JWT carrying the claims Grouper reads.

    No ``kid`` is set. Grouper ignores it -- ``GrouperPassword.getPublicKeyById``
    discards the id it is handed and returns the entity's stored public key --
    and the Java example on the wiki populates it with the private key itself,
    which would put the key on the wire in every request.
    """
    issued_at = int(time.time())
    payload = {'iat': issued_at, 'jti': str(uuid.uuid4())}
    if claims:
        payload.update(claims)
    if lifetime:
        payload['exp'] = issued_at + int(lifetime)

    signing_input = b'.'.join((
        _segment({'alg': 'RS256', 'typ': 'JWT'}),
        _segment(payload),
    ))
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return to_native(b'.'.join((signing_input, _b64url(signature))))


def bearer_token(prefix, private_key, claims=None, lifetime=None):
    """Return the Authorization value, less the leading ``Bearer`` word."""
    return normalise_prefix(prefix) + build_jwt(private_key, claims, lifetime)

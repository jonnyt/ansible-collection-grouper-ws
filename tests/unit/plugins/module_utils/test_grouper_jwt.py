# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Tests for the Grouper private key JWT bearer tokens.

The assertions here are written against Grouper's own server side code rather
than against a JWT library's idea of correctness, because Grouper is stricter
than the spec in one direction (iat is mandatory) and looser in another (it
ignores kid entirely).
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import json
import re
import time

import pytest

from ansible_collections.grouper.ws.plugins.module_utils.grouper_jwt import (
    GrouperJwtError,
    bearer_token,
    build_jwt,
    load_private_key,
    normalise_prefix,
)

cryptography = pytest.importorskip('cryptography')

from cryptography.exceptions import InvalidSignature                # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization    # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: E402

#: Copied verbatim from GrouperPublicPrivateKeyJwt.java. Every token this
#: module builds has to satisfy it or Grouper answers 401 with no explanation.
GROUPER_BEARER_RE = re.compile(r'^Bearer jwtUser_([^_]+)_(.*)$')

PREFIX = 'jwtUser_YWMyOTE5NGVkZTE4NDU1NzgxYmJhNjM0NjYwNTFlYzQ=_'


@pytest.fixture(scope='module')
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def encodings(key):
    """The four shapes a Grouper private key arrives in."""
    der = key.private_bytes(serialization.Encoding.DER,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    bare = base64.b64encode(der).decode()
    return {
        'pkcs8_pem': key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode(),
        'pkcs1_pem': key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()).decode(),
        # What the Grouper UI actually hands out.
        'bare_base64': bare,
        'wrapped_base64': '\n'.join(bare[i:i + 64] for i in range(0, len(bare), 64)),
    }


def b64url_json(part):
    """Decode one base64url JWT segment, restoring the stripped padding."""
    return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))


def segments(jwt):
    """Return the decoded header and payload of a bare JWT."""
    header_b64, payload_b64, unused_sig = jwt.split('.')
    return b64url_json(header_b64), b64url_json(payload_b64)


class TestLoadPrivateKey:

    @pytest.mark.parametrize('form', ['pkcs8_pem', 'pkcs1_pem',
                                      'bare_base64', 'wrapped_base64'])
    def test_every_form_grouper_or_openssl_produces_is_accepted(self, key, form):
        loaded = load_private_key(encodings(key)[form])
        assert loaded.private_numbers() == key.private_numbers()

    def test_bytes_are_accepted_as_well_as_text(self, key):
        blob = encodings(key)['pkcs8_pem'].encode()
        assert load_private_key(blob).private_numbers() == key.private_numbers()

    def test_surrounding_whitespace_is_ignored(self, key):
        blob = '\n  ' + encodings(key)['bare_base64'] + '  \n'
        assert load_private_key(blob).private_numbers() == key.private_numbers()

    def test_empty_key_is_named_as_such(self):
        with pytest.raises(GrouperJwtError, match='empty'):
            load_private_key('   ')

    def test_garbage_explains_the_accepted_forms(self):
        with pytest.raises(GrouperJwtError, match='Could not read'):
            load_private_key('not a key at all')

    def test_encrypted_key_is_rejected_with_a_readable_message(self, key):
        encrypted = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b'hunter2'))
        with pytest.raises(GrouperJwtError, match='Could not read'):
            load_private_key(encrypted)

    def test_non_rsa_key_is_rejected(self):
        # Grouper verifies with Algorithm.RSA256, so an EC key can never work.
        ec_key = ec.generate_private_key(ec.SECP256R1())
        pem = ec_key.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
        with pytest.raises(GrouperJwtError, match='RSA'):
            load_private_key(pem)


class TestNormalisePrefix:

    def test_prefix_from_the_ui_is_left_alone(self):
        assert normalise_prefix(PREFIX) == PREFIX

    def test_missing_trailing_underscore_is_added(self):
        assert normalise_prefix(PREFIX.rstrip('_')) == PREFIX

    def test_pasted_bearer_word_is_stripped(self):
        assert normalise_prefix('Bearer ' + PREFIX) == PREFIX

    def test_bearer_word_is_matched_regardless_of_case(self):
        assert normalise_prefix('  bearer  ' + PREFIX + ' ') == PREFIX

    def test_empty_prefix_is_named_as_such(self):
        with pytest.raises(GrouperJwtError, match='empty'):
            normalise_prefix('   ')


class TestBuildJwt:

    def test_algorithm_is_rs256(self, key):
        header, unused_payload = segments(build_jwt(key))
        assert header['alg'] == 'RS256'
        assert header['typ'] == 'JWT'

    def test_kid_is_absent(self, key):
        # Grouper's getPublicKeyById discards the id, and the example on the
        # wiki puts the private key in this field. Never send one.
        header, unused_payload = segments(build_jwt(key))
        assert 'kid' not in header

    def test_iat_is_present_and_current(self, key):
        # Grouper fails the request outright when iat is missing.
        unused_header, payload = segments(build_jwt(key))
        assert abs(payload['iat'] - int(time.time())) < 5

    def test_exp_is_omitted_by_default(self, key):
        unused_header, payload = segments(build_jwt(key))
        assert 'exp' not in payload

    def test_lifetime_sets_exp_relative_to_iat(self, key):
        unused_header, payload = segments(build_jwt(key, lifetime=120))
        assert payload['exp'] == payload['iat'] + 120

    def test_claims_are_merged_for_trusted_authority_use(self, key):
        claims = {'subjectSourceId': 'jdbc', 'subjectId': 'banderson'}
        unused_header, payload = segments(build_jwt(key, claims=claims))
        assert payload['subjectSourceId'] == 'jdbc'
        assert payload['subjectId'] == 'banderson'
        assert 'iat' in payload

    def test_each_call_mints_a_distinct_token(self, key):
        assert build_jwt(key) != build_jwt(key)

    def test_segments_carry_no_base64_padding(self, key):
        assert '=' not in build_jwt(key)

    def test_signature_verifies_against_the_public_key(self, key):
        jwt = build_jwt(key)
        signing_input, unused_dot, signature = jwt.rpartition('.')
        raw = base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4))
        key.public_key().verify(raw, signing_input.encode(),
                                padding.PKCS1v15(), hashes.SHA256())

    def test_a_tampered_payload_fails_verification(self, key):
        header_b64, payload_b64, signature = build_jwt(key).split('.')
        forged = base64.urlsafe_b64encode(
            json.dumps({'iat': 1}).encode()).rstrip(b'=').decode()
        raw = base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4))
        with pytest.raises(InvalidSignature):
            key.public_key().verify(
                raw, ('%s.%s' % (header_b64, forged)).encode(),
                padding.PKCS1v15(), hashes.SHA256())


class TestBearerToken:

    def test_header_matches_groupers_server_side_regex(self, key):
        header_value = 'Bearer ' + bearer_token(PREFIX, key)
        match = GROUPER_BEARER_RE.match(header_value)
        assert match is not None
        # Group 1 is base64 of the member id; Grouper base64-decodes it as-is.
        assert match.group(1) == 'YWMyOTE5NGVkZTE4NDU1NzgxYmJhNjM0NjYwNTFlYzQ='
        # Group 2 is what Grouper hands to JWT.decode, so it must stand alone.
        unused_header, payload = segments(match.group(2))
        assert 'iat' in payload

    def test_regex_still_matches_when_the_prefix_needed_fixing(self, key):
        header_value = 'Bearer ' + bearer_token('Bearer ' + PREFIX.rstrip('_'), key)
        assert GROUPER_BEARER_RE.match(header_value) is not None

    def test_a_key_loaded_from_grouper_form_produces_a_usable_token(self, key):
        loaded = load_private_key(encodings(key)['bare_base64'])
        assert GROUPER_BEARER_RE.match('Bearer ' + bearer_token(PREFIX, loaded))

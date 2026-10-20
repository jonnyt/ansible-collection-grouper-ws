# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  ws_url:
    description:
      - Base URL of the Grouper web services application, up to and including
        the context path, with no trailing C(/servicesRest).
      - For example C(https://grouper.example.edu/grouper-ws).
    type: str
    required: true
  api_version:
    description:
      - Grouper WS client API version used in the request path, for example
        C(v6_0_000) or C(v2_6_000).
      - This is the I(client) version. Grouper only emits a warning when the
        client version is newer than the server, so setting a version at or
        below the server version is always safe. Lower it to match older
        Grouper deployments.
    type: str
    default: v6_0_000
  username:
    description:
      - Username for HTTP Basic authentication.
      - Required when I(password) is set. Mutually exclusive with I(token).
    type: str
  password:
    description:
      - Password for HTTP Basic authentication. Mutually exclusive with I(token).
    type: str
  token:
    description:
      - Pre-issued bearer token sent verbatim in the HTTP C(Authorization)
        header, for Grouper deployments fronted by an OIDC or JWT aware proxy.
      - This token is used as supplied. To have Grouper's own JWT authentication
        signed for you, use I(jwt_prefix) with a private key instead.
      - Mutually exclusive with I(username)/I(password) and the I(jwt_*) options.
    type: str
  jwt_prefix:
    description:
      - Bearer token prefix identifying the Grouper entity that owns the private
        key, for example C(jwtUser_YWMyOTE5NGVkZTE4NDU1NzgxYmJhNjM0NjYwNTFlYzQ=_).
      - Copy it from the entity's page in the Grouper UI, where it is shown
        alongside the one-time private key download. A leading C(Bearer) word and
        a missing trailing underscore are both tolerated.
      - Trusted authority deployments use a C(jwtTrusted_<configId>_) prefix
        instead, together with I(jwt_claims).
      - Required when I(jwt_private_key) or I(jwt_private_key_path) is set.
    type: str
  jwt_private_key:
    description:
      - RSA private key used to sign the JWT, as key material rather than a path.
      - Accepts the bare base64 Grouper's UI downloads, or a PEM block in either
        PKCS#1 or PKCS#8 form. The key must not be passphrase protected.
      - Mutually exclusive with I(jwt_private_key_path).
    type: str
  jwt_private_key_path:
    description:
      - Path to a file holding the RSA private key, in any of the forms accepted
        by I(jwt_private_key).
      - Mutually exclusive with I(jwt_private_key).
    type: path
  jwt_claims:
    description:
      - Extra claims merged into the JWT payload.
      - Grouper's self-service JWT authentication needs none of these. Trusted
        authority configurations do, typically C(subjectSourceId) plus one of
        C(subjectId), C(subjectIdentifier) or C(subjectIdOrIdentifier), under
        whatever claim names that authority is configured to read.
    type: dict
  jwt_lifetime:
    description:
      - When set, adds an C(exp) claim this many seconds after the issue time.
      - Left unset by default. Grouper already bounds a token's age through
        C(iat) and C(grouper.selfService.jwt.maxValidTimeInSeconds), and a short
        C(exp) only adds sensitivity to clock skew between this host and the
        Grouper server.
    type: int
  act_as_subject_id:
    description:
      - Subject ID to act as. The authenticated account must be permitted to
        act as this subject in Grouper.
    type: str
  act_as_subject_identifier:
    description:
      - Subject identifier to act as, as an alternative to I(act_as_subject_id).
    type: str
  act_as_subject_source_id:
    description:
      - Subject source ID qualifying I(act_as_subject_id) or
        I(act_as_subject_identifier).
    type: str
  validate_certs:
    description:
      - Whether to validate the Grouper server TLS certificate.
      - Set to C(false) only against development stacks using self-signed
        certificates.
    type: bool
    default: true
  ca_path:
    description:
      - Path to a CA bundle used to validate the Grouper server certificate.
    type: path
  timeout:
    description:
      - Socket timeout in seconds for each web service call.
    type: int
    default: 60
requirements:
  - Grouper Web Services (grouper-ws) reachable over HTTP(S)
  - cryptography (only when using the I(jwt_*) options; it ships with ansible-core)
notes:
  - Authentication may be supplied through the environment instead of task
    arguments, using C(GROUPER_WS_URL), C(GROUPER_WS_API_VERSION),
    C(GROUPER_WS_USERNAME), C(GROUPER_WS_PASSWORD), C(GROUPER_WS_TOKEN),
    C(GROUPER_WS_JWT_PREFIX), C(GROUPER_WS_JWT_PRIVATE_KEY) and
    C(GROUPER_WS_JWT_PRIVATE_KEY_PATH).
  - A JWT is signed fresh for every web service call and never cached. Grouper
    rejects one whose issue time is older than
    C(grouper.selfService.jwt.maxValidTimeInSeconds), 600 seconds by default, so
    the clock on this host must be close to the Grouper server's.
  - The private key never leaves this host. Only the signature travels.
'''

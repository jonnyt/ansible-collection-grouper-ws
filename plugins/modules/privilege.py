#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: privilege
short_description: Manage one subject's privileges on an Internet2 Grouper folder or group
version_added: 0.1.0
description:
  - Sets exactly which privileges one subject, a person or a group, holds
    directly on a folder (a I(stem)) or on a group.
  - The listed privileges are granted and any other privilege the subject holds
    directly on that object is revoked. Privileges of every other subject are
    never touched.
  - Only direct grants are managed. A privilege the subject holds through a
    group it belongs to is not revoked, and a warning says so.
  - There is no member privilege. Membership is not managed by this
    collection; see M(grouper.ws.loader) and M(grouper.ws.jexl_script).
  - To have privileges granted on objects created inside a folder later, use
    M(grouper.ws.inherited_privilege).
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  stem:
    description:
      - Full colon delimited name of an existing folder.
      - Exactly one of I(stem) and I(group) is required.
    type: str
  group:
    description:
      - Full colon delimited name of an existing group.
    type: str
  privileges:
    description:
      - Every privilege the subject should hold directly on the object.
      - On a folder, any of C(admin), C(create), C(attr_read), C(attr_update)
        and C(view).
      - On a group, any of C(admin), C(update), C(read), C(view), C(optin),
        C(optout), C(attr_read) and C(attr_update).
      - An empty list revokes every privilege the subject holds directly on
        the object.
    type: list
    elements: str
    required: true
    choices: [admin, attr_read, attr_update, create, optin, optout, read, update, view]
extends_documentation_fragment:
  - grouper.ws.grouper
  - grouper.ws.subject
attributes:
  check_mode:
    description: Can run in check_mode and return changed status prediction without modifying target.
    support: full
  diff_mode:
    description: Will return details on what has changed (or possibly needs changing in check_mode), when in diff mode.
    support: full
notes:
  - >-
    A privilege granted by an inherited privilege rule is an ordinary direct
    grant once made. Listing a smaller set here for the same subject revokes
    it, and the rule does not put it back.
seealso:
  - module: grouper.ws.inherited_privilege
  - module: grouper.ws.stem
  - module: grouper.ws.group
'''

EXAMPLES = r'''
- name: Let the HR admins group administer the HR folder
  grouper.ws.privilege:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    stem: app:hr
    subject_group: app:hr:security:admins
    privileges: [admin, create, attr_read, attr_update, view]

- name: Let a person read and update a group
  grouper.ws.privilege:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    group: app:hr:groups:employees
    subject_identifier: jdoe
    subject_source_id: ldap
    privileges: [read, update, view]

- name: Take away everything a person was granted directly on a group
  grouper.ws.privilege:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    group: app:hr:groups:employees
    subject_identifier: jdoe
    privileges: []
'''

RETURN = r'''
privileges:
  description: The privileges the subject holds directly after this task.
  returned: success
  type: list
  elements: str
  sample: [read, update, view]
granted:
  description: Privileges granted by this task.
  returned: success
  type: list
  elements: str
  sample: [update]
revoked:
  description: Privileges revoked by this task.
  returned: success
  type: list
  elements: str
  sample: [optin]
subject:
  description: The subject as Grouper resolved it.
  returned: success
  type: dict
  sample:
    id: 0c6b5a8c4f8e4bfa9e1d2c3b4a5f6e7d
    name: admins
    sourceId: g:gsa
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.grouper.ws.plugins.module_utils.grouper import (
    GROUPER_MUTUALLY_EXCLUSIVE,
    GROUPER_REQUIRED_BY,
    GROUPER_REQUIRED_ONE_OF,
    GROUPER_REQUIRED_TOGETHER,
    SUBJECT_ARG_SPEC,
    SUBJECT_MUTUALLY_EXCLUSIVE,
    SUBJECT_REQUIRED_ONE_OF,
    GrouperClient,
    GrouperError,
    grouper_argument_spec,
    resolve_subject,
    subject_lookup,
)
from ansible_collections.grouper.ws.plugins.module_utils.privilege_spec import (
    GRANTED_CODES,
    PRIVILEGE_TYPES,
    REVOKED_CODES,
    STILL_EFFECTIVE_CODES,
    all_names,
    immediate_privileges,
    plan,
    result_codes,
    to_friendly,
    to_grouper,
)


def owner_lookups(owner_type, owner):
    """The getMemberships and assignGrouperPrivileges lookups for the owner."""
    if owner_type == 'stem':
        return ({'wsOwnerStemLookups': [{'stemName': owner}]},
                {'wsStemLookup': {'stemName': owner}})
    return ({'wsGroupLookups': [{'groupName': owner}]},
            {'wsGroupLookup': {'groupName': owner}})


def read_held(client, owner_type, owner, subject):
    """Grouper names of the privileges the subject holds directly on the owner."""
    lookup = owner_lookups(owner_type, owner)[0]
    body = dict(lookup,
                wsSubjectLookups=[{'subjectId': subject['id'],
                                   'subjectSourceId': subject['sourceId']}],
                fieldType=PRIVILEGE_TYPES[owner_type],
                memberFilter='Immediate')
    envelope = client.post('memberships', 'WsRestGetMembershipsRequest', body)
    return immediate_privileges(envelope.get('wsMemberships'), subject)


def assign(client, owner_type, owner, subject, privileges, allowed):
    """Grant or revoke privileges in one call; return {privilege: result code}."""
    body = dict(owner_lookups(owner_type, owner)[1],
                privilegeType=PRIVILEGE_TYPES[owner_type],
                privilegeNames=list(privileges),
                allowed='T' if allowed else 'F',
                wsSubjectLookups=[{'subjectId': subject['id'],
                                   'subjectSourceId': subject['sourceId']}])
    envelope = client.post('grouperPrivileges',
                           'WsRestAssignGrouperPrivilegesRequest', body)
    return result_codes(envelope)


def main():
    argument_spec = grouper_argument_spec(
        stem=dict(type='str'),
        group=dict(type='str'),
        privileges=dict(type='list', elements='str', required=True,
                        choices=all_names()),
    )
    argument_spec.update(SUBJECT_ARG_SPEC)
    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE + SUBJECT_MUTUALLY_EXCLUSIVE
        + [('stem', 'group')],
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF + SUBJECT_REQUIRED_ONE_OF
        + [('stem', 'group')],
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    params = module.params
    owner_type = 'stem' if params['stem'] else 'group'
    owner = params[owner_type]

    wanted, problems = to_grouper(params['privileges'], owner_type)
    if problems:
        module.fail_json(msg='Invalid privileges: %s' % '; '.join(problems))

    client = GrouperClient(module)

    try:
        subject = resolve_subject(client, subject_lookup(params))
        held = read_held(client, owner_type, owner, subject)
        to_grant, to_revoke = plan(wanted, held)

        diff = {
            'before': {'privileges': to_friendly(held, owner_type)},
            'after': {'privileges': to_friendly(wanted, owner_type)},
        }
        common = dict(subject=subject, diff=diff,
                      privileges=to_friendly(wanted, owner_type),
                      granted=to_friendly(to_grant, owner_type),
                      revoked=to_friendly(to_revoke, owner_type))

        if not to_grant and not to_revoke:
            module.exit_json(changed=False, **common)

        if module.check_mode:
            module.exit_json(changed=True, **common)

        changed = False
        if to_grant:
            codes = assign(client, owner_type, owner, subject, to_grant, True)
            changed |= any(code in GRANTED_CODES for code in codes.values())
        if to_revoke:
            codes = assign(client, owner_type, owner, subject, to_revoke, False)
            changed |= any(code in REVOKED_CODES for code in codes.values())
            still = sorted(name for name, code in codes.items()
                           if code in STILL_EFFECTIVE_CODES)
            if still:
                module.warn('%s still holds %s on %s through a group it belongs '
                            'to. Only direct grants are managed here.'
                            % (subject.get('name') or subject['id'],
                               ', '.join(to_friendly(still, owner_type)), owner))

        module.exit_json(changed=changed, **common)

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

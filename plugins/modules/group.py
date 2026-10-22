#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: group
short_description: Manage Internet2 Grouper groups
version_added: 0.1.0
description:
  - Creates or updates a Grouper group.
  - This module never manages group membership. Adding or removing members is
    deliberately out of scope so that a playbook run can never overwrite
    memberships that are owned by a loader, a provisioner, or a person. Use
    a loader definition, see M(grouper.ws.loader), when membership should
    be driven from a source of record.
  - Only attributes explicitly stated in the task are managed. Any attribute
    left unset is read from the existing group and written back unchanged.
  - This module never deletes groups.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  name:
    description:
      - Full colon delimited path of the group, for example
        C(app:hr:groups:employees).
    type: str
    required: true
  display_extension:
    description:
      - Human friendly name of this group within its folder.
      - Defaults to the last path component on creation.
    type: str
  description:
    description:
      - Free text description of the group.
    type: str
  type_of_group:
    description:
      - The kind of object to create.
      - Grouper cannot change this after creation, so it is only applied when
        the group is first created.
    type: str
    choices: [group, role, entity]
  create_parents:
    description:
      - Create any missing parent stems in the path.
    type: bool
    default: true
extends_documentation_fragment:
  - grouper.ws.grouper
attributes:
  check_mode:
    description: Can run in check_mode and return changed status prediction without modifying target.
    support: full
  diff_mode:
    description: Will return details on what has changed (or possibly needs changing in check_mode), when in diff mode.
    support: full
seealso:
  - module: grouper.ws.stem
  - module: grouper.ws.loader
  - module: grouper.ws.group_info
'''

EXAMPLES = r'''
- name: Create an empty group for HR employees
  grouper.ws.group:
    ws_url: https://grouper.example.edu/grouper-ws
    username: banderson
    password: "{{ grouper_ws_password }}"
    name: app:hr:groups:employees
    display_extension: Employees
    description: All active employees, loaded from the HR warehouse

- name: Create a role
  grouper.ws.group:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    name: app:hr:roles:approver
    type_of_group: role
'''

RETURN = r'''
group:
  description: The group as Grouper reports it after the save.
  returned: success
  type: dict
  sample:
    name: app:hr:groups:employees
    displayName: Applications:Human Resources:Groups:Employees
    displayExtension: Employees
    extension: employees
    description: All active employees
    typeOfGroup: group
    uuid: 09b488181c7d42ba9eb880fd7ad698d3
result_code:
  description:
    - Grouper's per-item save result code.
    - One of C(SUCCESS_INSERTED), C(SUCCESS_UPDATED) or
      C(SUCCESS_NO_CHANGES_NEEDED). Not returned in check mode.
  returned: success and not check mode
  type: str
  sample: SUCCESS_INSERTED
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.grouper.ws.plugins.module_utils.grouper import (
    GROUPER_MUTUALLY_EXCLUSIVE,
    GROUPER_REQUIRED_BY,
    GROUPER_REQUIRED_ONE_OF,
    GROUPER_REQUIRED_TOGETHER,
    GrouperClient,
    GrouperError,
    grouper_argument_spec,
    save_changed,
    save_needed,
    to_ws_bool,
)

#: Group fields this module compares and manages on an existing group.
MANAGED_FIELDS = ('displayExtension', 'description')


def find_group(client, name):
    """Return the group dict for an exact name, or None if it does not exist."""
    envelope = client.post('groups', 'WsRestFindGroupsRequest', {
        'wsQueryFilter': {
            'queryFilterType': 'FIND_BY_GROUP_NAME_EXACT',
            'groupName': name,
        },
    })
    for group in envelope.get('groupResults') or []:
        if group.get('name') == name:
            return group
    return None


def build_desired(module, current, name):
    """Merge requested values over current state, defaulting on creation."""
    params = module.params
    extension = name.split(':')[-1]

    desired = {}
    for field, requested in (('displayExtension', params['display_extension']),
                             ('description', params['description'])):
        if requested is not None:
            desired[field] = requested
        elif current is not None:
            desired[field] = current.get(field) or ''
        elif field == 'displayExtension':
            desired[field] = extension
        else:
            desired[field] = ''
    return desired


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            name=dict(type='str', required=True),
            display_extension=dict(type='str'),
            description=dict(type='str'),
            type_of_group=dict(type='str', choices=['group', 'role', 'entity']),
            create_parents=dict(type='bool', default=True),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE,
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF,
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    name = module.params['name']
    type_of_group = module.params['type_of_group']
    client = GrouperClient(module)

    try:
        current = find_group(client, name)

        if (current is not None and type_of_group
                and current.get('typeOfGroup') != type_of_group):
            module.warn(
                'Group %s already exists as typeOfGroup=%s; Grouper cannot '
                'change it to %s, so this setting is being ignored.'
                % (name, current.get('typeOfGroup'), type_of_group))

        desired = build_desired(module, current, name)
        changed = save_needed(current, desired, MANAGED_FIELDS)

        diff = {
            'before': {field: (current or {}).get(field, '')
                       for field in MANAGED_FIELDS} if current else {},
            'after': dict(desired),
        }

        if not changed:
            module.exit_json(changed=False, group=current, diff=diff,
                             result_code='SUCCESS_NO_CHANGES_NEEDED')

        if module.check_mode:
            module.exit_json(changed=True, group=current, diff=diff)

        ws_group = dict(desired)
        ws_group['name'] = name
        ws_group['extension'] = name.split(':')[-1]
        # Only meaningful at creation; Grouper rejects changing it later.
        if type_of_group and current is None:
            ws_group['typeOfGroup'] = type_of_group

        envelope = client.post('groups', 'WsRestGroupSaveRequest', {
            'wsGroupToSaves': [{
                'wsGroupLookup': {'groupName': name},
                'wsGroup': ws_group,
                'saveMode': 'INSERT_OR_UPDATE',
                'createParentStemsIfNotExist':
                    to_ws_bool(module.params['create_parents']),
            }],
        })

        results = envelope.get('results') or []
        if not results:
            module.fail_json(msg='Grouper returned no group save result for %s'
                                 % name)

        result = results[0]
        module.exit_json(
            changed=save_changed(result),
            group=result.get('wsGroup'),
            result_code=(result.get('resultMetadata') or {}).get('resultCode'),
            diff=diff,
        )

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

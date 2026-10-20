#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: group_info
short_description: Look up Internet2 Grouper groups
version_added: 0.1.0
description:
  - Reads Grouper groups.
  - This module reports group metadata only. It never returns or manages
    membership.
  - This module never changes anything and is safe in check mode.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  name:
    description:
      - Exact colon delimited group name to look up.
      - Returns an empty list when no such group exists, rather than failing.
    type: str
  stem:
    description:
      - Return the groups underneath this stem.
    type: str
  scope:
    description:
      - How deep to search below I(stem).
    type: str
    choices: [ONE_LEVEL, ALL_IN_SUBTREE]
    default: ALL_IN_SUBTREE
  name_contains:
    description:
      - Return groups whose name approximately matches this string.
    type: str
  type_of_groups:
    description:
      - Restrict results to these kinds of object.
    type: list
    elements: str
    choices: [group, role, entity]
extends_documentation_fragment:
  - grouper.ws.grouper
attributes:
  check_mode:
    description: Can run in check_mode and return changed status prediction without modifying target.
    support: full
  diff_mode:
    description: Will return details on what has changed (or possibly needs changing in check_mode), when in diff mode.
    support: none
seealso:
  - module: grouper.ws.group
'''

EXAMPLES = r'''
- name: Look up one group
  grouper.ws.group_info:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    name: app:hr:groups:employees
  register: employees

- name: List roles in a folder tree
  grouper.ws.group_info:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    stem: app:hr
    type_of_groups: [role]
'''

RETURN = r'''
groups:
  description: Matching groups, empty when nothing matched.
  returned: success
  type: list
  elements: dict
  sample:
    - name: app:hr:groups:employees
      displayName: Applications:Human Resources:Groups:Employees
      displayExtension: Employees
      extension: employees
      description: All active employees
      typeOfGroup: group
      uuid: 09b488181c7d42ba9eb880fd7ad698d3
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
)


def build_filter(params):
    if params['name']:
        query = {
            'queryFilterType': 'FIND_BY_GROUP_NAME_EXACT',
            'groupName': params['name'],
        }
    elif params['stem']:
        query = {
            'queryFilterType': 'FIND_BY_STEM_NAME',
            'stemName': params['stem'],
            'stemNameScope': params['scope'],
        }
    else:
        query = {
            'queryFilterType': 'FIND_BY_GROUP_NAME_APPROXIMATE',
            'groupName': params['name_contains'],
        }

    if params['type_of_groups']:
        query['typeOfGroups'] = ','.join(params['type_of_groups'])
    return query


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            name=dict(type='str'),
            stem=dict(type='str'),
            scope=dict(type='str', default='ALL_IN_SUBTREE',
                       choices=['ONE_LEVEL', 'ALL_IN_SUBTREE']),
            name_contains=dict(type='str'),
            type_of_groups=dict(type='list', elements='str',
                                choices=['group', 'role', 'entity']),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE + [
            ('name', 'stem', 'name_contains'),
        ],
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF + [
            ('name', 'stem', 'name_contains'),
        ],
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    client = GrouperClient(module)

    try:
        envelope = client.post('groups', 'WsRestFindGroupsRequest', {
            'wsQueryFilter': build_filter(module.params),
        })
        groups = envelope.get('groupResults') or []

        if module.params['name']:
            groups = [g for g in groups if g.get('name') == module.params['name']]

        module.exit_json(changed=False, groups=groups)

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: stem_info
short_description: Look up Internet2 Grouper folders (stems)
version_added: 0.1.0
description:
  - Reads Grouper folders, known in the Grouper API as stems.
  - This module never changes anything and is safe in check mode.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  name:
    description:
      - Exact colon delimited stem name to look up.
      - Returns an empty list when no such stem exists, rather than failing.
    type: str
  parent_stem:
    description:
      - Return the stems underneath this stem.
    type: str
  scope:
    description:
      - How deep to search below I(parent_stem).
    type: str
    choices: [ONE_LEVEL, ALL_IN_SUBTREE]
    default: ALL_IN_SUBTREE
  name_contains:
    description:
      - Return stems whose name approximately matches this string.
    type: str
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
  - module: grouper.ws.stem
'''

EXAMPLES = r'''
- name: Look up one folder
  grouper.ws.stem_info:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    name: app:hr:groups
  register: hr_groups

- name: Fail if the folder is missing
  ansible.builtin.assert:
    that: hr_groups.stems | length == 1

- name: List everything directly under a folder
  grouper.ws.stem_info:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    parent_stem: app:hr
    scope: ONE_LEVEL
'''

RETURN = r'''
stems:
  description: Matching stems, empty when nothing matched.
  returned: success
  type: list
  elements: dict
  sample:
    - name: app:hr:groups
      displayName: Applications:Human Resources:Groups
      displayExtension: Groups
      extension: groups
      description: Groups owned by Human Resources
      uuid: ff43c1b175aa438393934896604b75c6
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
        return {
            'stemQueryFilterType': 'FIND_BY_STEM_NAME',
            'stemName': params['name'],
        }
    if params['parent_stem']:
        return {
            'stemQueryFilterType': 'FIND_BY_PARENT_STEM_NAME',
            'parentStemName': params['parent_stem'],
            'parentStemNameScope': params['scope'],
        }
    return {
        'stemQueryFilterType': 'FIND_BY_STEM_NAME_APPROXIMATE',
        'stemName': params['name_contains'],
    }


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            name=dict(type='str'),
            parent_stem=dict(type='str'),
            scope=dict(type='str', default='ALL_IN_SUBTREE',
                       choices=['ONE_LEVEL', 'ALL_IN_SUBTREE']),
            name_contains=dict(type='str'),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE + [
            ('name', 'parent_stem', 'name_contains'),
        ],
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF + [
            ('name', 'parent_stem', 'name_contains'),
        ],
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    client = GrouperClient(module)

    try:
        envelope = client.post('stems', 'WsRestFindStemsRequest', {
            'wsStemQueryFilter': build_filter(module.params),
        })
        stems = envelope.get('stemResults') or []

        # FIND_BY_STEM_NAME is a prefix-ish match in some Grouper versions, so
        # pin an exact-name lookup to an exact result.
        if module.params['name']:
            stems = [s for s in stems if s.get('name') == module.params['name']]

        module.exit_json(changed=False, stems=stems)

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

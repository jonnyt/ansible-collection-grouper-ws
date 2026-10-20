#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: stem
short_description: Manage Internet2 Grouper folders (stems)
version_added: 0.1.0
description:
  - Creates or updates a Grouper folder, known in the Grouper API as a stem.
  - Only attributes explicitly stated in the task are managed. Any attribute
    left unset is read from the existing stem and written back unchanged, so
    this module will not blank out a description set elsewhere.
  - This module never deletes stems.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  name:
    description:
      - Full colon delimited path of the stem, for example C(app:hr:groups).
    type: str
    required: true
  display_extension:
    description:
      - Human friendly name of this stem within its parent.
      - Defaults to the last path component on creation.
    type: str
  description:
    description:
      - Free text description of the stem.
    type: str
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
  - module: grouper.ws.group
  - module: grouper.ws.stem_info
'''

EXAMPLES = r'''
- name: Create the HR folder tree
  grouper.ws.stem:
    ws_url: https://grouper.example.edu/grouper-ws
    username: banderson
    password: "{{ grouper_ws_password }}"
    name: app:hr:groups
    display_extension: Groups
    description: Groups owned by Human Resources

- name: Create a folder without touching an existing description
  grouper.ws.stem:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    name: app:hr:reference

- name: Authenticate as a local entity with its downloaded private key
  grouper.ws.stem:
    ws_url: "{{ grouper_ws_url }}"
    jwt_prefix: "{{ grouper_ws_jwt_prefix }}"
    jwt_private_key_path: ~/.grouper/ansible-entity.key
    name: app:hr:reference
'''

RETURN = r'''
stem:
  description: The stem as Grouper reports it after the save.
  returned: success
  type: dict
  sample:
    name: app:hr:groups
    displayName: Applications:Human Resources:Groups
    displayExtension: Groups
    extension: groups
    description: Groups owned by Human Resources
    uuid: ff43c1b175aa438393934896604b75c6
result_code:
  description:
    - Grouper's per-item save result code.
    - One of C(SUCCESS_INSERTED), C(SUCCESS_UPDATED) or
      C(SUCCESS_NO_CHANGES_NEEDED). Not returned in check mode.
  returned: success and not check mode
  type: str
  sample: SUCCESS_NO_CHANGES_NEEDED
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
    to_ws_bool,
)

#: Stem fields this module compares and manages.
MANAGED_FIELDS = ('displayExtension', 'description')


def find_stem(client, name):
    """Return the stem dict for an exact name, or None if it does not exist."""
    envelope = client.post('stems', 'WsRestFindStemsRequest', {
        'wsStemQueryFilter': {
            'stemQueryFilterType': 'FIND_BY_STEM_NAME',
            'stemName': name,
        },
    })
    for stem in envelope.get('stemResults') or []:
        if stem.get('name') == name:
            return stem
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


def needs_change(current, desired):
    if current is None:
        return True
    return any((current.get(field) or '') != desired[field]
               for field in MANAGED_FIELDS)


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            name=dict(type='str', required=True),
            display_extension=dict(type='str'),
            description=dict(type='str'),
            create_parents=dict(type='bool', default=True),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE,
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF,
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    name = module.params['name']
    client = GrouperClient(module)

    try:
        current = find_stem(client, name)
        desired = build_desired(module, current, name)
        changed = needs_change(current, desired)

        diff = {
            'before': {field: (current or {}).get(field, '')
                       for field in MANAGED_FIELDS} if current else {},
            'after': dict(desired),
        }

        if not changed:
            module.exit_json(changed=False, stem=current, diff=diff,
                             result_code='SUCCESS_NO_CHANGES_NEEDED')

        if module.check_mode:
            module.exit_json(changed=True, stem=current, diff=diff)

        ws_stem = dict(desired)
        ws_stem['name'] = name
        ws_stem['extension'] = name.split(':')[-1]

        envelope = client.post('stems', 'WsRestStemSaveRequest', {
            'wsStemToSaves': [{
                'wsStemLookup': {'stemName': name},
                'wsStem': ws_stem,
                'saveMode': 'INSERT_OR_UPDATE',
                'createParentStemsIfNotExist':
                    to_ws_bool(module.params['create_parents']),
            }],
        })

        results = envelope.get('results') or []
        if not results:
            module.fail_json(msg='Grouper returned no stem save result for %s'
                                 % name)

        result = results[0]
        module.exit_json(
            changed=save_changed(result),
            stem=result.get('wsStem'),
            result_code=(result.get('resultMetadata') or {}).get('resultCode'),
            diff=diff,
        )

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: jexl_script
short_description: Manage Internet2 Grouper JEXL scripted (ABAC) groups
version_added: 0.1.0
description:
  - Attaches or updates a JEXL script on an existing group, so that Grouper
    computes the group's membership from the script. This is Grouper's
    attribute based access control, for example
    C(${entity.memberOf('ref:staff') && !entity.memberOf('ref:lockout')}).
  - The script is stored as an attribute assigned I(on) the marker
    C(etc:attribute:abacJexlScript:grouperJexlScriptMarker), which is itself
    assigned to the group.
  - The group must already exist. Use M(grouper.ws.group) to create it.
  - A group already driven by a SQL or LDAP loader is refused. Grouper drives
    a group from one loader at a time, and this module will not remove the
    other one.
  - This module never adds or removes members itself. Grouper's JEXL daemons
    own the resulting membership.
  - This module never removes a script.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  group:
    description:
      - Full colon delimited name of an existing group to attach the script to.
    type: str
    required: true
  script:
    description:
      - The JEXL script deciding membership, evaluated against each C(entity).
      - Written with or without its C(${...}) wrapper; Grouper accepts both.
        Leading and trailing whitespace is removed, as the UI does.
      - Grouper validates almost nothing on write, so a script that does not
        parse is only reported later, by the daemon.
    type: str
    required: true
  subject_source_ids:
    description:
      - Subject sources whose entities the script is evaluated over.
      - Omit to leave the stored value alone. An empty list removes it, which
        means Grouper's global default sources.
      - Stored sorted and comma separated, as the UI stores it.
      - Grouper ignores this, and silently uses the global defaults, unless
        per group overrides are enabled and every id is in its list of
        available sources.
    type: list
    elements: str
  jexl_script_stem:
    description:
      - Stem holding the JEXL script attributes. Grouper builds it from
        C(grouper.rootStemForBuiltinObjects), so override this only if that
        has been retuned.
    type: str
    default: 'etc:attribute:abacJexlScript'
  attribute_root_stem:
    description:
      - Override for Grouper's C(grouper.attribute.rootStem). Used only to find
        an LDAP loader that would conflict.
    type: str
    default: 'etc:attribute'
  legacy_attribute_stem:
    description:
      - Override for Grouper's C(legacyAttribute.baseStem). Used only to find a
        SQL loader that would conflict.
    type: str
    default: 'etc:legacy:attribute'
extends_documentation_fragment:
  - grouper.ws.grouper
attributes:
  check_mode:
    description: Can run in check_mode and return changed status prediction without modifying target.
    support: full
  diff_mode:
    description: Will return details on what has changed (or possibly needs changing in check_mode), when in diff mode.
    support: full
notes:
  - >-
    Unlike a SQL or LDAP loader, nothing needs scheduling. The
    C(grouperLoaderJexlScriptIncremental) change log consumer recalculates a
    group as soon as its script changes, every minute by default, and the
    daily C(grouperLoaderJexlScriptFullSync) job rescans every script.
  - >-
    The UI's script analysis and its maximum membership size limits are UI
    checks only. Writing through web services bypasses them, so test a new
    script in the UI's Loader tab before deploying it widely.
  - >-
    The account needs to update the group's attributes and the attribute
    definitions under I(jexl_script_stem). In practice that usually means a
    member of the wheel group.
seealso:
  - module: grouper.ws.group
  - module: grouper.ws.loader
'''

EXAMPLES = r'''
- name: Create the group the script will drive
  grouper.ws.group:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    name: app:vpn:groups:allowed
    description: Staff who are not locked out, computed by Grouper

- name: Compute membership from other groups
  grouper.ws.jexl_script:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    group: app:vpn:groups:allowed
    script: >-
      ${entity.memberOf('ref:staff') && !entity.memberOf('ref:lockout')}

- name: Evaluate the script over one subject source only
  grouper.ws.jexl_script:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    group: app:vpn:groups:allowed
    script: >-
      ${entity.memberOf('ref:staff') && !entity.memberOf('ref:lockout')}
    subject_source_ids:
      - ldap
'''

RETURN = r'''
jexl_script:
  description:
    - The script attribute names and values as this task intends them, keyed
      by fully qualified Grouper attribute def name.
  returned: success
  type: dict
  sample:
    etc:attribute:abacJexlScript:grouperJexlScriptJexlScript: >-
      ${entity.memberOf('ref:staff')}
marker:
  description: Fully qualified name of the JEXL script marker attribute.
  returned: success
  type: str
  sample: etc:attribute:abacJexlScript:grouperJexlScriptMarker
changed_attributes:
  description: Attribute def names that were added or updated.
  returned: success
  type: list
  elements: str
removed_attributes:
  description:
    - Attribute def names that were removed, only ever the subject source ids
      when I(subject_source_ids) is an empty list.
  returned: success
  type: list
  elements: str
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
from ansible_collections.grouper.ws.plugins.module_utils.jexl_spec import (
    DEFAULT_JEXL_SCRIPT_STEM,
    JexlNaming,
    conflict_message,
    plan_changes,
    validate_script,
)
from ansible_collections.grouper.ws.plugins.module_utils.loader_spec import (
    LoaderNaming,
)
from ansible_collections.grouper.ws.plugins.module_utils.marker_assign import (
    build_batch,
    find_markers,
    read_current,
)


def loader_marker_names(params):
    """Markers of the SQL and LDAP loader families, which conflict with a script."""
    return [
        LoaderNaming(loader_type,
                     attribute_root_stem=params['attribute_root_stem'],
                     legacy_attribute_stem=params['legacy_attribute_stem']).marker_name
        for loader_type in ('SQL_SIMPLE', 'LDAP_SIMPLE')
    ]


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            group=dict(type='str', required=True),
            script=dict(type='str', required=True),
            subject_source_ids=dict(type='list', elements='str'),
            jexl_script_stem=dict(type='str', default=DEFAULT_JEXL_SCRIPT_STEM),
            attribute_root_stem=dict(type='str', default='etc:attribute'),
            legacy_attribute_stem=dict(type='str', default='etc:legacy:attribute'),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE,
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF,
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    params = module.params
    group = params['group']

    errors = validate_script(params['script'])
    if errors:
        module.fail_json(msg='Invalid JEXL script: %s' % '; '.join(errors))

    naming = JexlNaming(params['jexl_script_stem'])
    client = GrouperClient(module)

    try:
        conflicts = find_markers(client, group, loader_marker_names(params))
        if conflicts:
            module.fail_json(msg=conflict_message(group, conflicts))

        marker, current = read_current(client, group, naming.marker_name)
        desired, to_write, to_remove = plan_changes(
            params['script'], params['subject_source_ids'], current, naming)

        changed = bool(to_write or to_remove or marker is None)

        diff = {
            'before': dict(current),
            'after': dict(current),
        }
        diff['after'].update(desired)
        for name in to_remove:
            diff['after'].pop(name, None)

        common = dict(jexl_script=desired, marker=naming.marker_name,
                      changed_attributes=sorted(to_write), diff=diff,
                      removed_attributes=list(to_remove))

        if not changed:
            module.exit_json(changed=False, **common)

        if module.check_mode:
            module.exit_json(changed=True, **common)

        client.post('attributeAssignments',
                    'WsRestAssignAttributesBatchRequest',
                    {'wsAssignAttributeBatchEntries':
                        build_batch(group, naming.marker_name, to_write, to_remove)})

        module.exit_json(changed=True, **common)

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

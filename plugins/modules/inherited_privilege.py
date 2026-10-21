#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: inherited_privilege
short_description: Manage privileges inherited by objects inside an Internet2 Grouper folder
version_added: 0.1.0
description:
  - Sets which privileges one subject, a person or a group, receives on the
    folders, groups and attribute definitions created inside a folder. This
    is the folder's B(Inherited privileges) tab in the Grouper UI.
  - Each of I(folder_privileges), I(group_privileges) and
    I(attribute_def_privileges) is one Grouper rule on the folder. A list that
    is given becomes exactly that rule's privileges. A list that is left out
    leaves its rule alone.
  - A rule is identified by the folder, the kind of object, the subject and
    I(name_pattern). Changing I(scope) or the privileges updates the rule in
    place.
  - This module never removes a rule, so an empty list is refused.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  stem:
    description:
      - Full colon delimited name of an existing folder to attach the rules to.
    type: str
    required: true
  scope:
    description:
      - C(sub) applies to objects anywhere below the folder, C(one) only to its
        direct children.
    type: str
    choices: [one, sub]
    default: sub
  name_pattern:
    description:
      - Only objects whose full name matches this SQL C(LIKE) pattern receive
        the privileges, for example C(app:hr:%:admins).
      - Part of the rule's identity, so a different pattern is a separate rule.
    type: str
  folder_privileges:
    description:
      - Privileges on folders created inside I(stem).
    type: list
    elements: str
    choices: [admin, create, attr_read, attr_update, view]
  group_privileges:
    description:
      - Privileges on groups created inside I(stem).
    type: list
    elements: str
    choices: [admin, update, read, view, optin, optout, attr_read, attr_update]
  attribute_def_privileges:
    description:
      - Privileges on attribute definitions created inside I(stem).
    type: list
    elements: str
    choices: [admin, update, read, view, optin, optout, attr_read, attr_update]
  attribute_root_stem:
    description:
      - Override for Grouper's C(grouper.attribute.rootStem). The rule
        attributes live under its C(rules) folder.
    type: str
    default: 'etc:attribute'
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
    Objects created after the rule is written receive the privileges as they
    are created. Objects that already exist receive them the next time
    Grouper's rules daemon runs, which is C(otherJob.rules), daily at 7am by
    default. The UI applies them at once, and web services have no equivalent
    call.
  - >-
    Taking a privilege out of a rule stops it being granted to new objects. It
    does not revoke it from objects that already received it. Use
    M(grouper.ws.privilege) for those.
  - >-
    Rules act as GrouperSystem, as the UI's rules do. Grouper allows that for
    members of the wheel group, for members of C(rules.act.as.group), and for
    anyone who can write the rule when
    C(rules.allowActAsGrouperSystemForInheritedStemPrivileges) is on, which it
    is by default. The account also needs to update the folder's attributes.
seealso:
  - module: grouper.ws.privilege
  - module: grouper.ws.stem
'''

EXAMPLES = r'''
- name: HR admins administer everything created under the HR folder
  grouper.ws.inherited_privilege:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    stem: app:hr
    subject_group: app:hr:security:admins
    folder_privileges: [admin, create]
    group_privileges: [admin]
    attribute_def_privileges: [admin]

- name: Auditors can read groups directly inside the reports folder
  grouper.ws.inherited_privilege:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    stem: app:hr:reports
    scope: one
    subject_group: app:audit:auditors
    group_privileges: [read, view]

- name: Only for groups named like approvers
  grouper.ws.inherited_privilege:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    stem: app:hr
    name_pattern: "app:hr:%approvers"
    subject_identifier: jdoe
    subject_source_id: ldap
    group_privileges: [update, read, view]
'''

RETURN = r'''
rules:
  description:
    - Each managed rule after this task, keyed by C(folder), C(group) or
      C(attribute_def).
    - C(id) is the rule's attribute assignment id. It is absent in check mode
      for a rule not yet created.
  returned: success
  type: dict
  sample:
    group:
      id: 66d23d80f7004c3e9ad23f280dac3941
      scope: sub
      privileges: [read, view]
changed_rules:
  description: The kinds of object whose rule was created or updated.
  returned: success
  type: list
  elements: str
  sample: [group]
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
from ansible_collections.grouper.ws.plugins.module_utils.marker_assign import (
    build_batch,
    read_all,
)
from ansible_collections.grouper.ws.plugins.module_utils.privilege_spec import (
    PRIVILEGES,
    to_friendly,
    to_grouper,
)
from ansible_collections.grouper.ws.plugins.module_utils.rule_spec import (
    OBJECT_TYPES,
    VALID,
    RuleNaming,
    duplicate_message,
    matching_rules,
    plan_rule,
    summary,
)

#: Option holding each object type's privilege list.
OPTIONS = (
    ('folder', 'folder_privileges'),
    ('group', 'group_privileges'),
    ('attribute_def', 'attribute_def_privileges'),
)


def friendly_summary(settings, object_type):
    """A rule's scope and privileges in the names a task uses."""
    view = summary(settings)
    if view:
        view['privileges'] = to_friendly(view['privileges'],
                                         OBJECT_TYPES[object_type][2])
    return view


def read_rules(client, naming, stem):
    """Every rule on the stem, with settings keyed by short name."""
    return [(marker, naming.short(settings))
            for marker, settings in read_all(client, stem, naming.marker_name)]


def find_rule(module, rules, stem, object_type, subject, identifier):
    """The one rule this task manages for an object type, or (None, None)."""
    matches = matching_rules(rules, object_type, subject,
                             module.params['name_pattern'], identifier)
    if len(matches) > 1:
        module.fail_json(msg=duplicate_message(
            stem, object_type, [marker for marker, unused in matches]))
    return matches[0] if matches else (None, None)


def main():
    argument_spec = grouper_argument_spec(
        stem=dict(type='str', required=True),
        scope=dict(type='str', choices=['one', 'sub'], default='sub'),
        name_pattern=dict(type='str'),
        folder_privileges=dict(type='list', elements='str',
                               choices=sorted(PRIVILEGES['stem'])),
        group_privileges=dict(type='list', elements='str',
                              choices=sorted(PRIVILEGES['group'])),
        attribute_def_privileges=dict(type='list', elements='str',
                                      choices=sorted(PRIVILEGES['attribute_def'])),
        attribute_root_stem=dict(type='str', default='etc:attribute'),
    )
    argument_spec.update(SUBJECT_ARG_SPEC)
    module = AnsibleModule(
        argument_spec=argument_spec,
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE + SUBJECT_MUTUALLY_EXCLUSIVE,
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF + SUBJECT_REQUIRED_ONE_OF
        + [tuple(option for unused, option in OPTIONS)],
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    params = module.params
    stem = params['stem']
    scope = params['scope'].upper()

    requested = {}
    for object_type, option in OPTIONS:
        if params[option] is None:
            continue
        if not params[option]:
            module.fail_json(msg='%s must not be empty. An empty rule would '
                                 'mean removing it, and this module never '
                                 'removes a rule.' % option)
        requested[object_type] = to_grouper(params[option],
                                            OBJECT_TYPES[object_type][2])[0]

    naming = RuleNaming(params['attribute_root_stem'])
    identifier = params['subject_identifier'] or params['subject_group']
    client = GrouperClient(module)

    try:
        subject = resolve_subject(client, subject_lookup(params))
        rules = read_rules(client, naming, stem)

        plans = {}
        for object_type, privileges in requested.items():
            marker, current = find_rule(module, rules, stem, object_type,
                                        subject, identifier)
            desired, to_write = plan_rule(current, object_type, subject, scope,
                                          privileges, params['name_pattern'])
            plans[object_type] = (marker, current, desired, to_write)

        changed_rules = sorted(object_type for object_type, plan in plans.items()
                               if plan[3])
        diff = {
            'before': dict((object_type, friendly_summary(plan[1], object_type))
                           for object_type, plan in plans.items()),
            'after': dict((object_type, friendly_summary(plan[2], object_type))
                          for object_type, plan in plans.items()),
        }
        result = dict(diff['after'])
        for object_type, plan in plans.items():
            if plan[0] is not None:
                result[object_type] = dict(result[object_type], id=plan[0].get('id'))
        common = dict(subject=subject, diff=diff, changed_rules=changed_rules,
                      rules=result)

        if not changed_rules:
            module.exit_json(changed=False, **common)

        if module.check_mode:
            module.exit_json(changed=True, **common)

        for object_type in changed_rules:
            marker, current, unused_desired, to_write = plans[object_type]
            entries = build_batch(
                stem, naming.marker_name,
                dict((naming.name(key), value) for key, value in to_write.items()),
                [], owner_type='stem',
                existing_id=marker.get('id') if marker else None,
                add_new=marker is None)
            client.post('attributeAssignments',
                        'WsRestAssignAttributesBatchRequest',
                        {'wsAssignAttributeBatchEntries': entries})

        # Grouper's rules hook judges each rule as it is written. Read the
        # verdict back, as RuleApi.assertRuleValid does after its own writes.
        rules = read_rules(client, naming, stem)
        for object_type in changed_rules:
            marker, settings = find_rule(module, rules, stem, object_type,
                                         subject, identifier)
            if marker is None:
                module.fail_json(msg='The %s rule on %s was written but could '
                                     'not be read back.' % (object_type, stem),
                                 **common)
            result[object_type] = dict(result[object_type], id=marker.get('id'))
            if settings.get(VALID) != 'T':
                module.fail_json(msg='Grouper rejected the %s rule on %s: %s'
                                     % (object_type, stem,
                                        settings.get(VALID) or 'no verdict'),
                                 **common)

        module.exit_json(changed=True, **common)

    except GrouperError as exc:
        module.fail_json(msg=exc.message, status=exc.status)


if __name__ == '__main__':
    main()

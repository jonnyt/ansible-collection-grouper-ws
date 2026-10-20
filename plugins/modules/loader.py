#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: loader
short_description: Manage Internet2 Grouper loader definitions on a group
version_added: 0.1.0
description:
  - Attaches or updates a Grouper loader definition on an existing group, so
    that group membership is maintained by Grouper from a SQL query or an LDAP
    search rather than by hand.
  - Grouper stores loader settings in two different frameworks and this module
    hides the difference. SQL loaders use the legacy attribute framework under
    C(etc:legacy:attribute), keyed off the C(grouperLoader) group type. LDAP
    loaders use the modern attribute framework under
    C(etc:attribute:loaderLdap). In both cases the individual settings are
    attribute assignments made I(on) the marker assignment, not on the group.
  - The group must already exist. Use M(grouper.ws.group) to create it.
  - This module writes the loader B(definition) only. It cannot schedule,
    enable, or run the resulting job, because the Grouper Web Services API
    exposes no loader, daemon or scheduling operation of any kind. See the
    notes below for how the job actually gets scheduled.
  - This module never adds or removes members itself.
  - This module never removes a loader definition.
author:
  - Jonathon Taylor (@jonathontaylor)
options:
  group:
    description:
      - Full colon delimited name of an existing group to attach the loader to.
    type: str
    required: true
  type:
    description:
      - The Grouper loader type.
      - C(SQL_GROUP_LIST) and C(LDAP_GROUP_LIST) drive many groups from one
        definition. C(SQL_SIMPLE) and C(LDAP_SIMPLE) drive only this group.
    type: str
    required: true
    choices:
      - SQL_SIMPLE
      - SQL_GROUP_LIST
      - LDAP_SIMPLE
      - LDAP_GROUP_LIST
      - LDAP_GROUPS_FROM_ATTRIBUTES
  sql:
    description:
      - Settings for the C(SQL_SIMPLE) and C(SQL_GROUP_LIST) loader types.
      - Required when I(type) is a SQL type, and rejected otherwise.
    type: dict
    suboptions:
      database:
        description:
          - Name of the database connection from C(grouper-loader.properties),
            for example C(grouper) for Grouper's own database.
        type: str
      query:
        description:
          - The membership query.
          - For C(SQL_SIMPLE) it must return a C(SUBJECT_ID) column, optionally
            C(SUBJECT_SOURCE_ID).
          - For C(SQL_GROUP_LIST) it must also return a C(GROUP_NAME) column.
        type: str
      group_query:
        description:
          - Optional query for C(SQL_GROUP_LIST) returning C(GROUP_NAME) and
            optionally C(GROUP_DISPLAY_NAME) and C(GROUP_DESCRIPTION), used to
            create groups and set their metadata.
        type: str
      schedule_type:
        description:
          - How the loader job is scheduled.
        type: str
        choices: [CRON, START_TO_START_INTERVAL]
      quartz_cron:
        description:
          - Quartz cron expression, required when I(sql.schedule_type) is
            C(CRON). For example C(0 0 7 * * ?) for daily at 07:00.
        type: str
      interval_seconds:
        description:
          - Seconds between runs, required when I(sql.schedule_type) is
            C(START_TO_START_INTERVAL).
        type: int
      priority:
        description:
          - Quartz thread priority for this job.
        type: int
      and_groups:
        description:
          - Groups that a subject must also be a member of to be loaded.
            Effectively intersects the query result with these groups.
        type: list
        elements: str
      group_types:
        description:
          - Group types to assign to groups created by a C(SQL_GROUP_LIST) job.
        type: list
        elements: str
      groups_like:
        description:
          - SQL LIKE pattern identifying groups this job manages, so that
            groups no longer returned by the query can be emptied or removed.
        type: str
  ldap:
    description:
      - Settings for the C(LDAP_SIMPLE), C(LDAP_GROUP_LIST) and
        C(LDAP_GROUPS_FROM_ATTRIBUTES) loader types.
      - Required when I(type) is an LDAP type, and rejected otherwise.
    type: dict
    suboptions:
      server_id:
        description:
          - LDAP connection id from C(grouper-loader.properties).
        type: str
      filter:
        description:
          - LDAP search filter.
        type: str
      search_dn:
        description:
          - Base DN for the search, relative to the server's configured base.
        type: str
      search_scope:
        description:
          - LDAP search scope.
        type: str
        choices: [OBJECT_SCOPE, ONELEVEL_SCOPE, SUBTREE_SCOPE]
      subject_attribute:
        description:
          - Attribute on the LDAP result holding the subject id.
          - For C(LDAP_GROUP_LIST) this is the multi valued membership
            attribute, for example C(hasMember).
        type: str
      subject_id_type:
        description:
          - How to interpret the subject attribute value.
        type: str
        choices: [subjectId, subjectIdentifier, subjectIdOrIdentifier]
      subject_expression:
        description:
          - Optional expression to transform each subject attribute value
            before resolving it, for example to strip a DN down to a uid.
        type: str
      source_id:
        description:
          - Restrict subject resolution to this subject source id.
        type: str
      quartz_cron:
        description:
          - Quartz cron expression. LDAP loaders are cron scheduled only.
        type: str
      priority:
        description:
          - Quartz thread priority for this job.
        type: int
      and_groups:
        description:
          - Groups that a subject must also be a member of to be loaded.
        type: list
        elements: str
      groups_like:
        description:
          - Pattern identifying groups this job manages, so that groups no
            longer returned can be emptied or removed.
        type: str
      group_types:
        description:
          - Group types to assign to groups created by this job.
        type: list
        elements: str
      group_attribute:
        description:
          - Attribute holding the group name.
          - Required for C(LDAP_GROUPS_FROM_ATTRIBUTES), where each value of
            this attribute becomes a group.
        type: str
      group_name_expression:
        description:
          - Expression producing the Grouper group name for each result, for
            example C(${stemName}:${groupAttribute}).
        type: str
      group_display_name_expression:
        description:
          - Expression producing the group display name.
          - Not supported by C(LDAP_SIMPLE).
        type: str
      group_description_expression:
        description:
          - Expression producing the group description.
        type: str
      group_attribute_processing_expression:
        description:
          - Expression applied to each group attribute value before use.
        type: str
      attribute_filter_expression:
        description:
          - Expression deciding whether an attribute value should be processed.
        type: str
      extra_attributes:
        description:
          - Additional LDAP attributes to retrieve for use in expressions.
        type: list
        elements: str
      results_transformation_class:
        description:
          - Fully qualified Java class transforming results before loading.
        type: str
      admins:
        description:
          - Subjects or groups granted the admin privilege on loaded groups.
        type: list
        elements: str
      readers:
        description:
          - Subjects or groups granted the read privilege on loaded groups.
        type: list
        elements: str
      updaters:
        description:
          - Subjects or groups granted the update privilege on loaded groups.
        type: list
        elements: str
      viewers:
        description:
          - Subjects or groups granted the view privilege on loaded groups.
        type: list
        elements: str
      optins:
        description:
          - Subjects or groups granted the optin privilege on loaded groups.
        type: list
        elements: str
      optouts:
        description:
          - Subjects or groups granted the optout privilege on loaded groups.
        type: list
        elements: str
      group_attr_readers:
        description:
          - Subjects or groups granted attribute read on loaded groups.
        type: list
        elements: str
      group_attr_updaters:
        description:
          - Subjects or groups granted attribute update on loaded groups.
        type: list
        elements: str
  purge_unmanaged:
    description:
      - Remove loader settings that exist on the group but are not stated in
        this task.
      - Useful when switching, for example, from a cron schedule to an
        interval, where a stale C(quartz_cron) would otherwise remain.
      - Only attributes belonging to this loader's own attribute namespace are
        ever removed.
    type: bool
    default: false
  attribute_root_stem:
    description:
      - Override for Grouper's C(grouper.attribute.rootStem), which is where
        LDAP loader attributes live.
    type: str
    default: 'etc:attribute'
  legacy_attribute_stem:
    description:
      - Override for Grouper's C(legacyAttribute.baseStem), which is where SQL
        loader attributes live.
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
    Writing the definition does not create the scheduler job. Grouper turns
    loader definitions into Quartz jobs in C(GrouperLoader.scheduleJobs()),
    which runs only when the loader B(daemon starts). No built-in daemon job
    rescans for definitions added later, so a loader attached by this module
    stays unscheduled, and reports as not enabled, until one of the following
    happens.
  - Restart the Grouper loader daemon. This is the usual answer for a
    playbook driven workflow, and it picks up every pending definition at once.
  - >-
    Open the group's Loader tab in the Grouper UI and save it. The UI's save
    action calls C(validateAndScheduleSqlLoad) or
    C(validateAndScheduleLdapLoad) directly, which schedules just that job.
  - >-
    Schedule it from GSH, which runs inside Grouper and can reach the
    scheduler, for example C(loaderRunOneJob) or C(GrouperLoader.scheduleJobs()).
  - >-
    The UI's Enable and Disable buttons on a loader job are Quartz
    C(resumeJob) and C(pauseJob) calls against an B(already scheduled) job.
    A job this module has just defined is not paused, it does not exist in the
    scheduler yet, which is a different state with the same outward symptom.
seealso:
  - module: grouper.ws.group
'''

EXAMPLES = r'''
- name: Drive one group from a SQL query
  grouper.ws.loader:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    group: app:hr:groups:employees
    type: SQL_SIMPLE
    sql:
      database: grouper
      schedule_type: CRON
      quartz_cron: "0 0 7 * * ?"
      query: >-
        select net_id as SUBJECT_ID
        from hr_employee
        where status = 'A'

- name: Build a tree of department groups from one SQL query
  grouper.ws.loader:
    ws_url: "{{ grouper_ws_url }}"
    username: banderson
    password: "{{ grouper_ws_password }}"
    group: app:hr:groups:departments
    type: SQL_GROUP_LIST
    purge_unmanaged: true
    sql:
      database: grouper
      schedule_type: START_TO_START_INTERVAL
      interval_seconds: 3600
      groups_like: "app:hr:groups:departments:%"
      query: >-
        select net_id as SUBJECT_ID,
               'app:hr:groups:departments:' || dept_code as GROUP_NAME
        from hr_employee
        where status = 'A'
      group_query: >-
        select 'app:hr:groups:departments:' || dept_code as GROUP_NAME,
               dept_name as GROUP_DISPLAY_NAME
        from hr_department

- name: Load members of one group from an LDAP group object
  grouper.ws.loader:
    ws_url: "{{ grouper_ws_url }}"
    token: "{{ grouper_ws_token }}"
    group: app:ldap:groups:staff
    type: LDAP_SIMPLE
    ldap:
      server_id: personLdap
      quartz_cron: "0 15 * * * ?"
      search_dn: ou=groups
      filter: "(cn=staff)"
      subject_attribute: hasMember
      subject_id_type: subjectIdentifier
'''

RETURN = r'''
loader:
  description:
    - The loader attribute names and values as this task intends them, keyed
      by fully qualified Grouper attribute def name.
  returned: success
  type: dict
  sample:
    etc:legacy:attribute:legacyAttribute_grouperLoaderType: SQL_SIMPLE
    etc:legacy:attribute:legacyAttribute_grouperLoaderDbName: grouper
marker:
  description: Fully qualified name of the marker attribute for this loader type.
  returned: success
  type: str
  sample: etc:legacy:attribute:legacyGroupType_grouperLoader
changed_attributes:
  description: Attribute def names that were added or updated.
  returned: success
  type: list
  elements: str
removed_attributes:
  description:
    - Attribute def names that were removed, only ever non empty when
      I(purge_unmanaged) is C(true).
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
from ansible_collections.grouper.ws.plugins.module_utils.loader_spec import (
    LOADER_TYPES,
    SEARCH_SCOPES,
    SCHEDULE_TYPES,
    SUBJECT_ID_TYPES,
    LoaderNaming,
    build_desired_attributes,
    is_sql,
    validate_options,
)

SQL_SUBOPTIONS = dict(
    database=dict(type='str'),
    query=dict(type='str'),
    group_query=dict(type='str'),
    schedule_type=dict(type='str', choices=list(SCHEDULE_TYPES)),
    quartz_cron=dict(type='str'),
    interval_seconds=dict(type='int'),
    priority=dict(type='int'),
    and_groups=dict(type='list', elements='str'),
    group_types=dict(type='list', elements='str'),
    groups_like=dict(type='str'),
)

LDAP_SUBOPTIONS = dict(
    server_id=dict(type='str'),
    filter=dict(type='str'),
    search_dn=dict(type='str'),
    search_scope=dict(type='str', choices=list(SEARCH_SCOPES)),
    subject_attribute=dict(type='str'),
    subject_id_type=dict(type='str', choices=list(SUBJECT_ID_TYPES)),
    subject_expression=dict(type='str'),
    source_id=dict(type='str'),
    quartz_cron=dict(type='str'),
    priority=dict(type='int'),
    and_groups=dict(type='list', elements='str'),
    groups_like=dict(type='str'),
    group_types=dict(type='list', elements='str'),
    group_attribute=dict(type='str'),
    group_name_expression=dict(type='str'),
    group_display_name_expression=dict(type='str'),
    group_description_expression=dict(type='str'),
    group_attribute_processing_expression=dict(type='str'),
    attribute_filter_expression=dict(type='str'),
    extra_attributes=dict(type='list', elements='str'),
    results_transformation_class=dict(type='str'),
    admins=dict(type='list', elements='str'),
    readers=dict(type='list', elements='str'),
    updaters=dict(type='list', elements='str'),
    viewers=dict(type='list', elements='str'),
    optins=dict(type='list', elements='str'),
    optouts=dict(type='list', elements='str'),
    group_attr_readers=dict(type='list', elements='str'),
    group_attr_updaters=dict(type='list', elements='str'),
)


def read_current(client, group, marker_name):
    """Return (marker assignment, {attribute def name: value}) for the group.

    The marker is assigned to the group itself; every setting is assigned on
    the marker assignment, so settings are matched by ownerAttributeAssignId.
    """
    envelope = client.post(
        'attributeAssignments', 'WsRestGetAttributeAssignmentsRequest', {
            'attributeAssignType': 'group',
            'wsOwnerGroupLookups': [{'groupName': group}],
            'wsAttributeDefNameLookups': [{'name': marker_name}],
            'includeAssignmentsOnAssignments': 'T',
        })

    assigns = envelope.get('wsAttributeAssigns') or []

    marker = None
    for assign in assigns:
        if (assign.get('attributeAssignType') == 'group'
                and assign.get('attributeDefNameName') == marker_name
                and assign.get('ownerGroupName') == group):
            marker = assign
            break

    if marker is None:
        return None, {}

    values = {}
    for assign in assigns:
        if assign.get('ownerAttributeAssignId') != marker.get('id'):
            continue
        name = assign.get('attributeDefNameName')
        if not name:
            continue
        assign_values = assign.get('wsAttributeAssignValues') or []
        values[name] = assign_values[0].get('valueSystem', '') if assign_values else ''
    return marker, values


def build_batch(group, marker_name, to_write, to_remove):
    """Build assignAttributesBatch entries.

    Entry 0 assigns the marker to the group and every other entry references
    it by batchIndex, so a brand new loader and an update to an existing one
    take exactly the same shape and a single round trip.
    """
    entries = [{
        'wsOwnerGroupLookup': {'groupName': group},
        'attributeAssignType': 'group',
        'attributeAssignOperation': 'assign_attr',
        'wsAttributeDefNameLookup': {'name': marker_name},
    }]

    for name in sorted(to_write):
        entries.append({
            'wsOwnerAttributeAssignLookup': {'batchIndex': '0'},
            'attributeAssignType': 'group_asgn',
            'attributeAssignOperation': 'assign_attr',
            'wsAttributeDefNameLookup': {'name': name},
            'attributeAssignValueOperation': 'replace_values',
            'values': [{'valueSystem': to_write[name]}],
        })

    for name in sorted(to_remove):
        entries.append({
            'wsOwnerAttributeAssignLookup': {'batchIndex': '0'},
            'attributeAssignType': 'group_asgn',
            'attributeAssignOperation': 'remove_attr',
            'wsAttributeDefNameLookup': {'name': name},
        })

    return entries


def main():
    module = AnsibleModule(
        argument_spec=grouper_argument_spec(
            group=dict(type='str', required=True),
            type=dict(type='str', required=True, choices=list(LOADER_TYPES)),
            sql=dict(type='dict', options=SQL_SUBOPTIONS),
            ldap=dict(type='dict', options=LDAP_SUBOPTIONS),
            purge_unmanaged=dict(type='bool', default=False),
            attribute_root_stem=dict(type='str', default='etc:attribute'),
            legacy_attribute_stem=dict(type='str', default='etc:legacy:attribute'),
        ),
        mutually_exclusive=GROUPER_MUTUALLY_EXCLUSIVE + [('sql', 'ldap')],
        required_together=GROUPER_REQUIRED_TOGETHER,
        required_one_of=GROUPER_REQUIRED_ONE_OF,
        required_by=GROUPER_REQUIRED_BY,
        supports_check_mode=True,
    )

    params = module.params
    group = params['group']
    loader_type = params['type']
    sql_wanted = is_sql(loader_type)

    suite = params['sql'] if sql_wanted else params['ldap']
    wrong_suite = params['ldap'] if sql_wanted else params['sql']
    suite_name = 'sql' if sql_wanted else 'ldap'

    if wrong_suite is not None:
        module.fail_json(
            msg="loader type %s takes its settings under '%s', not '%s'"
                % (loader_type, suite_name, 'ldap' if sql_wanted else 'sql'))
    if suite is None:
        module.fail_json(
            msg="loader type %s requires the '%s' settings"
                % (loader_type, suite_name))

    errors = validate_options(loader_type, suite)
    if errors:
        module.fail_json(msg='Invalid loader definition: %s' % '; '.join(errors))

    naming = LoaderNaming(
        loader_type,
        attribute_root_stem=params['attribute_root_stem'],
        legacy_attribute_stem=params['legacy_attribute_stem'],
    )
    desired = build_desired_attributes(loader_type, suite, naming)

    client = GrouperClient(module)

    try:
        marker, current = read_current(client, group, naming.marker_name)

        to_write = {name: value for name, value in desired.items()
                    if current.get(name) != value}

        to_remove = []
        if params['purge_unmanaged']:
            # Only ever remove attributes from this loader's own namespace.
            managed_prefix = naming.attribute_name('')
            known = set(naming.attribute_name(ext)
                        for ext in naming.option_map.values())
            known.add(naming.type_attribute_name)
            to_remove = sorted(
                name for name in current
                if name not in desired
                and name.startswith(managed_prefix)
                and name in known)

        changed = bool(to_write or to_remove or marker is None)

        diff = {
            'before': dict(current),
            'after': dict(current),
        }
        diff['after'].update(desired)
        for name in to_remove:
            diff['after'].pop(name, None)

        common = dict(loader=desired, marker=naming.marker_name,
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

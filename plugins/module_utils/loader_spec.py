# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Schema describing how Grouper loader definitions map onto attributes.

Grouper stores loader configuration in two different places depending on the
loader type, and both use *assignment on assignment*:

SQL loaders (``SQL_SIMPLE``, ``SQL_GROUP_LIST``)
    Use the legacy attribute framework. The group carries the legacy group
    type marker ``etc:legacy:attribute:legacyGroupType_grouperLoader``, and
    each setting is an attribute such as
    ``etc:legacy:attribute:legacyAttribute_grouperLoaderQuery`` assigned *on
    that marker assignment*.

LDAP loaders (``LDAP_SIMPLE``, ``LDAP_GROUP_LIST``, ``LDAP_GROUPS_FROM_ATTRIBUTES``)
    Use the modern attribute framework. The group carries the marker
    ``etc:attribute:loaderLdap:grouperLoaderLdap`` and each setting is an
    attribute such as ``etc:attribute:loaderLdap:grouperLoaderLdapFilter``
    assigned *on that marker assignment*.

The names, the required/optional split and the enum values below were taken
from ``GrouperLoader.java``, ``GrouperLoaderType.java`` and
``LoaderLdapUtils.java`` in the Grouper source tree.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

# Default built-in stems. Overridable because a site may retune
# grouper.rootStemForBuiltinObjects / grouper.attribute.rootStem.
DEFAULT_ATTRIBUTE_ROOT_STEM = 'etc:attribute'
DEFAULT_LEGACY_ATTRIBUTE_STEM = 'etc:legacy:attribute'

LEGACY_GROUP_TYPE_PREFIX = 'legacyGroupType_'
LEGACY_ATTRIBUTE_PREFIX = 'legacyAttribute_'

SQL_GROUP_TYPE = 'grouperLoader'
LDAP_MARKER_EXTENSION = 'grouperLoaderLdap'
LDAP_SUBSTEM = 'loaderLdap'

SQL_TYPES = ('SQL_SIMPLE', 'SQL_GROUP_LIST')
LDAP_TYPES = ('LDAP_SIMPLE', 'LDAP_GROUP_LIST', 'LDAP_GROUPS_FROM_ATTRIBUTES')
LOADER_TYPES = SQL_TYPES + LDAP_TYPES

SCHEDULE_TYPES = ('CRON', 'START_TO_START_INTERVAL')
SEARCH_SCOPES = ('OBJECT_SCOPE', 'ONELEVEL_SCOPE', 'SUBTREE_SCOPE')
SUBJECT_ID_TYPES = ('subjectId', 'subjectIdentifier', 'subjectIdOrIdentifier')

# Ansible option name -> Grouper legacy attribute extension (unprefixed).
SQL_ATTRIBUTE_MAP = {
    'database': 'grouperLoaderDbName',
    'query': 'grouperLoaderQuery',
    'group_query': 'grouperLoaderGroupQuery',
    'schedule_type': 'grouperLoaderScheduleType',
    'quartz_cron': 'grouperLoaderQuartzCron',
    'interval_seconds': 'grouperLoaderIntervalSeconds',
    'priority': 'grouperLoaderPriority',
    'and_groups': 'grouperLoaderAndGroups',
    'group_types': 'grouperLoaderGroupTypes',
    'groups_like': 'grouperLoaderGroupsLike',
    'delete_previously_managed_groups': 'grouperLoaderDeletePreviouslyManagedGroups',
}

#: The loader type itself is stored as an attribute like any other.
SQL_TYPE_ATTRIBUTE = 'grouperLoaderType'

# Ansible option name -> Grouper LDAP loader attribute extension.
LDAP_ATTRIBUTE_MAP = {
    'server_id': 'grouperLoaderLdapServerId',
    'filter': 'grouperLoaderLdapFilter',
    'search_dn': 'grouperLoaderLdapSearchDn',
    'search_scope': 'grouperLoaderLdapSearchScope',
    'subject_attribute': 'grouperLoaderLdapSubjectAttribute',
    'subject_id_type': 'grouperLoaderLdapSubjectIdType',
    'subject_expression': 'grouperLoaderLdapSubjectExpression',
    'source_id': 'grouperLoaderLdapSourceId',
    'quartz_cron': 'grouperLoaderLdapQuartzCron',
    'priority': 'grouperLoaderLdapPriority',
    'and_groups': 'grouperLoaderLdapAndGroups',
    'groups_like': 'grouperLoaderLdapGroupsLike',
    'delete_previously_managed_groups':
        'grouperLoaderLdapDeletePreviouslyManagedGroups',
    'group_types': 'grouperLoaderLdapGroupTypes',
    'group_attribute': 'grouperLoaderLdapGroupAttribute',
    'group_name_expression': 'grouperLoaderLdapGroupNameExpression',
    'group_display_name_expression': 'grouperLoaderLdapGroupDisplayNameExpression',
    'group_description_expression': 'grouperLoaderLdapGroupDescriptionExpression',
    'group_attribute_processing_expression':
        'grouperLoaderLdapGroupAttributeProcessingExpression',
    'attribute_filter_expression': 'grouperLoaderLdapAttributeFilterExpression',
    'extra_attributes': 'grouperLoaderLdapExtraAttributes',
    'results_transformation_class': 'grouperLoaderLdapResultsTransformationClass',
    'admins': 'grouperLoaderLdapAdmins',
    'readers': 'grouperLoaderLdapReaders',
    'updaters': 'grouperLoaderLdapUpdaters',
    'viewers': 'grouperLoaderLdapViewers',
    'optins': 'grouperLoaderLdapOptins',
    'optouts': 'grouperLoaderLdapOptouts',
    'group_attr_readers': 'grouperLoaderLdapGroupAttrReaders',
    'group_attr_updaters': 'grouperLoaderLdapGroupAttrUpdaters',
}

LDAP_TYPE_ATTRIBUTE = 'grouperLoaderLdapType'

# Required Ansible option names per loader type, from
# GrouperLoaderType#attributeRequired. The loader type attribute itself is
# always written by the module, so it is not listed here.
REQUIRED_OPTIONS = {
    'SQL_SIMPLE': ('database', 'query', 'schedule_type'),
    'SQL_GROUP_LIST': ('database', 'query', 'schedule_type'),
    'LDAP_SIMPLE': ('server_id', 'filter', 'quartz_cron', 'subject_attribute'),
    'LDAP_GROUP_LIST': ('server_id', 'filter', 'quartz_cron', 'subject_attribute'),
    'LDAP_GROUPS_FROM_ATTRIBUTES':
        ('server_id', 'filter', 'quartz_cron', 'group_attribute'),
}

# Options each loader type accepts, from GrouperLoaderType#attributeOptional
# plus the required set. Note that GrouperLoaderType only lists a subset for
# the SQL types; grouperLoaderGroupQuery / GroupTypes / GroupsLike are defined
# by the grouperLoader group type and are genuinely valid for SQL_GROUP_LIST,
# so they are allowed here.
_SQL_COMMON = ('database', 'query', 'schedule_type', 'quartz_cron',
               'interval_seconds', 'priority', 'and_groups')

_LDAP_COMMON = ('server_id', 'filter', 'search_dn', 'search_scope',
                'subject_attribute', 'subject_id_type', 'subject_expression',
                'source_id', 'quartz_cron', 'priority', 'and_groups',
                'extra_attributes', 'admins', 'readers', 'updaters',
                'viewers', 'optins', 'optouts')

# LDAP_SIMPLE deliberately excludes group_display_name_expression: Grouper's
# source marks grouperLoaderLdapGroupDisplayExtensionExpression as "not
# allowed" for this type, and there is no display-name variant registered.
ALLOWED_OPTIONS = {
    'SQL_SIMPLE': frozenset(_SQL_COMMON),
    'SQL_GROUP_LIST': frozenset(
        _SQL_COMMON + ('group_query', 'group_types', 'groups_like',
                       'delete_previously_managed_groups')),
    'LDAP_SIMPLE': frozenset(
        _LDAP_COMMON + ('group_attribute', 'group_name_expression',
                        'group_description_expression')),
    'LDAP_GROUP_LIST': frozenset(
        _LDAP_COMMON + ('group_attribute', 'group_name_expression',
                        'group_display_name_expression',
                        'group_description_expression', 'group_types',
                        'groups_like', 'delete_previously_managed_groups',
                        'group_attr_readers', 'group_attr_updaters')),
    'LDAP_GROUPS_FROM_ATTRIBUTES': frozenset(
        _LDAP_COMMON + ('group_attribute', 'group_name_expression',
                        'group_display_name_expression',
                        'group_description_expression',
                        'group_attribute_processing_expression',
                        'attribute_filter_expression',
                        'results_transformation_class', 'group_types',
                        'groups_like', 'delete_previously_managed_groups',
                        'group_attr_readers', 'group_attr_updaters')),
}


# Options stored as Grouper booleans. The UI writes "T" (UiV2GrouperLoader),
# and GrouperUtil.booleanValue also accepts true/false, so stored values are
# normalised before comparing.
BOOLEAN_OPTIONS = ('delete_previously_managed_groups',)

_TRUE_STRINGS = ('t', 'true', 'y', 'yes')
_FALSE_STRINGS = ('f', 'false', 'n', 'no')


def is_sql(loader_type):
    return loader_type in SQL_TYPES


class LoaderNaming(object):
    """Resolves fully qualified attribute names for a loader type."""

    def __init__(self, loader_type, attribute_root_stem=None,
                 legacy_attribute_stem=None):
        self.loader_type = loader_type
        self.sql = is_sql(loader_type)
        self.attribute_root_stem = (
            attribute_root_stem or DEFAULT_ATTRIBUTE_ROOT_STEM).rstrip(':')
        self.legacy_attribute_stem = (
            legacy_attribute_stem or DEFAULT_LEGACY_ATTRIBUTE_STEM).rstrip(':')

    @property
    def marker_name(self):
        """Attribute def name of the marker assigned directly to the group."""
        if self.sql:
            return '%s:%s%s' % (self.legacy_attribute_stem,
                                LEGACY_GROUP_TYPE_PREFIX, SQL_GROUP_TYPE)
        return '%s:%s:%s' % (self.attribute_root_stem, LDAP_SUBSTEM,
                             LDAP_MARKER_EXTENSION)

    def attribute_name(self, extension):
        """Attribute def name of a setting, assigned on the marker assignment."""
        if self.sql:
            return '%s:%s%s' % (self.legacy_attribute_stem,
                                LEGACY_ATTRIBUTE_PREFIX, extension)
        return '%s:%s:%s' % (self.attribute_root_stem, LDAP_SUBSTEM, extension)

    @property
    def type_attribute_name(self):
        return self.attribute_name(
            SQL_TYPE_ATTRIBUTE if self.sql else LDAP_TYPE_ATTRIBUTE)

    @property
    def option_map(self):
        return SQL_ATTRIBUTE_MAP if self.sql else LDAP_ATTRIBUTE_MAP


def build_desired_attributes(loader_type, options, naming):
    """Return {attribute_def_name: value} for the settings the user declared.

    ``options`` is the ``sql`` or ``ldap`` suboption dict. ``None`` values are
    skipped so the module only manages what the playbook actually states.
    """
    desired = {naming.type_attribute_name: loader_type}
    option_map = naming.option_map
    for option, value in sorted(options.items()):
        if value is None:
            continue
        desired[naming.attribute_name(option_map[option])] = _stringify(value)
    return desired


def _stringify(value):
    """Grouper attribute values are always strings."""
    if isinstance(value, bool):
        return 'T' if value else 'F'
    if isinstance(value, (list, tuple)):
        return ', '.join(str(item) for item in value)
    return str(value)


def normalize_current(current, naming):
    """Return ``current`` with boolean settings rewritten as ``T`` / ``F``.

    Only used for comparison, so a loader saved with ``true`` (or by the UI as
    ``T``) does not report a change.
    """
    boolean_names = set(naming.attribute_name(naming.option_map[option])
                        for option in BOOLEAN_OPTIONS)
    normalized = dict(current)
    for name in boolean_names & set(current):
        value = (current[name] or '').strip().lower()
        if value in _TRUE_STRINGS:
            normalized[name] = 'T'
        elif value in _FALSE_STRINGS:
            normalized[name] = 'F'
    return normalized


def implied_removals(options, naming, current):
    """Settings that must be removed for the declared ones to take effect.

    Grouper ignores delete-previously-managed-groups while a groups-like string
    is stored (GrouperLoaderType#syncGroupList), and the UI blanks the like
    string when the option is switched on. Do the same.
    """
    if options.get('delete_previously_managed_groups') is not True:
        return []
    groups_like = naming.attribute_name(naming.option_map['groups_like'])
    return [groups_like] if groups_like in current else []


def validate_options(loader_type, options):
    """Return a list of human readable validation errors."""
    errors = []
    supplied = set(name for name, value in options.items() if value is not None)

    allowed = ALLOWED_OPTIONS[loader_type]
    for name in sorted(supplied - allowed):
        errors.append(
            "option '%s' is not supported by loader type %s (supported: %s)"
            % (name, loader_type, ', '.join(sorted(allowed))))

    for name in REQUIRED_OPTIONS[loader_type]:
        if name not in supplied:
            errors.append(
                "option '%s' is required by loader type %s" % (name, loader_type))

    if (options.get('delete_previously_managed_groups')
            and options.get('groups_like') is not None):
        errors.append(
            "'delete_previously_managed_groups' and 'groups_like' are mutually "
            "exclusive; delete_previously_managed_groups is Grouper's "
            "replacement for groups_like")

    if loader_type in SQL_TYPES:
        schedule = options.get('schedule_type')
        if schedule == 'CRON' and not options.get('quartz_cron'):
            errors.append(
                "schedule_type 'CRON' requires 'quartz_cron'")
        if (schedule == 'START_TO_START_INTERVAL'
                and not options.get('interval_seconds')):
            errors.append(
                "schedule_type 'START_TO_START_INTERVAL' requires "
                "'interval_seconds'")

    return errors

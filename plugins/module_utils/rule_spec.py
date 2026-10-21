# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""How inherited privileges on a stem map onto Grouper rules.

Inherited privileges are not privileges. They are Grouper rules: the marker
``<attribute root>:rules:rule`` assigned to the stem, with every setting
assigned *on that marker assignment* (``stem_asgn``). The rule marker may be
assigned to a stem many times over, one rule per subject and object type.

The settings written here are exactly the ones ``RuleApi.inheritGroupPrivileges``,
``inheritFolderPrivileges`` and ``inheritAttributeDefPrivileges`` write, and
nothing else. That matters: ``RuleSubjectActAs.allowedToActAs`` lets a
non-wheel caller have a rule act as GrouperSystem only when the rule has
exactly this shape (and ``rules.allowActAsGrouperSystemForInheritedStemPrivileges``
is on, as it is by default).

``ruleValid`` is computed by Grouper's rules hook as the values are written.
It reads ``T`` or an explanation, and is never written here.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.grouper.ws.plugins.module_utils.privilege_spec import (
    normalise,
)

RULE_MARKER = 'rule'
ACT_AS_SOURCE_ID = 'ruleActAsSubjectSourceId'
ACT_AS_SUBJECT_ID = 'ruleActAsSubjectId'
CHECK_TYPE = 'ruleCheckType'
CHECK_STEM_SCOPE = 'ruleCheckStemScope'
IF_CONDITION_ENUM = 'ruleIfConditionEnum'
IF_CONDITION_ARG0 = 'ruleIfConditionEnumArg0'
THEN_ENUM = 'ruleThenEnum'
THEN_ARG0 = 'ruleThenEnumArg0'
THEN_ARG1 = 'ruleThenEnumArg1'
VALID = 'ruleValid'

NAME_MATCHES = 'nameMatchesSqlLikeString'

#: Rules act as GrouperSystem, as RuleApi has them do.
ROOT_SOURCE_ID = 'g:isa'
ROOT_SUBJECT_ID = 'GrouperSystem'

#: Object type -> (ruleCheckType, ruleThenEnum, privilege_spec owner type).
OBJECT_TYPES = {
    'folder': ('stemCreate', 'assignStemPrivilegeToStemId', 'stem'),
    'group': ('groupCreate', 'assignGroupPrivilegeToGroupId', 'group'),
    'attribute_def': ('attributeDefCreate',
                      'assignAttributeDefPrivilegeToAttributeDefId',
                      'attribute_def'),
}


class RuleNaming(object):
    """Resolves fully qualified rule attribute names.

    ``RuleUtils.attributeRuleStemName()`` appends ``:rules`` to
    ``grouper.attribute.rootStem``.
    """

    def __init__(self, attribute_root_stem=None):
        self.stem = '%s:rules' % (attribute_root_stem or 'etc:attribute').rstrip(':')

    def name(self, extension):
        return '%s:%s' % (self.stem, extension)

    @property
    def marker_name(self):
        return self.name(RULE_MARKER)

    def short(self, settings):
        """Strip the rules stem from a settings dict's keys."""
        prefix = self.stem + ':'
        return dict((key[len(prefix):], value) for key, value in settings.items()
                    if key.startswith(prefix))


def parse_subject(packed):
    """Parse a rule's packed subject string, as SubjectFinder does.

    Returns (source id or None, kind, value), where kind is ``id``,
    ``identifier`` or ``id_or_identifier``. The longest separator is checked
    first, as in ``findByPackedSubjectString``.
    """
    packed = (packed or '').strip()
    for separator, kind in (('::::::::', 'id_or_identifier'),
                            ('::::::', 'identifier'),
                            ('::::', 'id')):
        if separator in packed:
            parts = [part.strip() for part in packed.split(separator)]
            parts = [part for part in parts if part]
            if len(parts) > 1:
                return parts[0], kind, parts[1]
            return None, kind, parts[0] if parts else ''
    return None, 'id_or_identifier', packed


def subject_matches(packed, subject, identifier=None):
    """Whether a packed subject string names the resolved subject.

    An identifier can only be matched when the task gave one, since Grouper
    does not return a subject's identifiers.
    """
    source, kind, value = parse_subject(packed)
    if source and source != subject.get('sourceId'):
        return False
    if kind in ('id', 'id_or_identifier') and value == subject.get('id'):
        return True
    if kind in ('identifier', 'id_or_identifier') and identifier and value == identifier:
        return True
    return False


def pack_subject(subject):
    """The form RuleApi writes: ``sourceId :::: subjectId``."""
    return '%s :::: %s' % (subject['sourceId'], subject['id'])


def split_privileges(value):
    return set(normalise(item) for item in (value or '').split(',') if item.strip())


def join_privileges(privileges):
    """Comma and space joined, as Privilege.stringValue renders a set."""
    return ', '.join(sorted(privileges))


def matching_rules(rules, object_type, subject, name_pattern, identifier=None):
    """Return the (marker, settings) pairs that are this task's rule.

    A rule is identified by its object type, subject and name pattern. Scope
    and privileges are what the task manages, so changing either updates the
    rule in place. ``rules`` holds settings keyed by short name.
    """
    check_type, then_enum, unused_owner = OBJECT_TYPES[object_type]
    found = []
    for marker, settings in rules:
        if settings.get(CHECK_TYPE) != check_type or settings.get(THEN_ENUM) != then_enum:
            continue
        if not subject_matches(settings.get(THEN_ARG0), subject, identifier):
            continue
        condition = settings.get(IF_CONDITION_ENUM) or ''
        if condition and condition != NAME_MATCHES:
            continue
        pattern = (settings.get(IF_CONDITION_ARG0) or '') if condition else ''
        if pattern != (name_pattern or ''):
            continue
        found.append((marker, settings))
    return found


def plan_rule(current, object_type, subject, scope, privileges, name_pattern):
    """Return (desired, to_write) settings, keyed by short name.

    A new rule is written whole. An existing one only has its scope and
    privileges rewritten; its subject string and act-as are left as found,
    since they already identify the same subject.
    """
    check_type, then_enum, unused_owner = OBJECT_TYPES[object_type]
    desired = {
        CHECK_STEM_SCOPE: scope,
        THEN_ARG1: join_privileges(privileges),
    }

    if current is None:
        desired.update({
            ACT_AS_SOURCE_ID: ROOT_SOURCE_ID,
            ACT_AS_SUBJECT_ID: ROOT_SUBJECT_ID,
            CHECK_TYPE: check_type,
            THEN_ENUM: then_enum,
            THEN_ARG0: pack_subject(subject),
        })
        if name_pattern:
            desired[IF_CONDITION_ENUM] = NAME_MATCHES
            desired[IF_CONDITION_ARG0] = name_pattern
        return desired, dict(desired)

    to_write = {}
    if current.get(CHECK_STEM_SCOPE) != scope:
        to_write[CHECK_STEM_SCOPE] = scope
    if split_privileges(current.get(THEN_ARG1)) != set(privileges):
        to_write[THEN_ARG1] = desired[THEN_ARG1]
    return desired, to_write


def summary(settings):
    """The task-facing view of a rule: scope and privilege list."""
    if settings is None:
        return {}
    return {
        'scope': (settings.get(CHECK_STEM_SCOPE) or '').lower(),
        'privileges': sorted(split_privileges(settings.get(THEN_ARG1))),
    }


def duplicate_message(stem, object_type, markers):
    return ('Stem %s has %d rules granting %s privileges to this subject (%s). '
            'This module will not guess which one to manage, and never removes '
            'a rule, so remove the extras in the Grouper UI first.'
            % (stem, len(markers), object_type.replace('_', ' '),
               ', '.join(sorted(marker.get('id') or '?' for marker in markers))))

# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.grouper.ws.plugins.module_utils import rule_spec as rs

SUBJECT = {'id': 'abc123', 'sourceId': 'g:gsa'}


def group_rule(arg0='g:gsa :::: abc123', scope='SUB', privileges='read, view',
               **extra):
    settings = {
        rs.ACT_AS_SOURCE_ID: 'g:isa',
        rs.ACT_AS_SUBJECT_ID: 'GrouperSystem',
        rs.CHECK_TYPE: 'groupCreate',
        rs.CHECK_STEM_SCOPE: scope,
        rs.THEN_ENUM: 'assignGroupPrivilegeToGroupId',
        rs.THEN_ARG0: arg0,
        rs.THEN_ARG1: privileges,
        rs.VALID: 'T',
    }
    settings.update(extra)
    return settings


class TestNaming:

    def test_default(self):
        naming = rs.RuleNaming()
        assert naming.marker_name == 'etc:attribute:rules:rule'
        assert naming.name(rs.THEN_ARG1) == 'etc:attribute:rules:ruleThenEnumArg1'

    def test_custom_root(self):
        assert rs.RuleNaming('my:attrs:').marker_name == 'my:attrs:rules:rule'

    def test_short_names(self):
        naming = rs.RuleNaming()
        assert naming.short({'etc:attribute:rules:ruleValid': 'T',
                             'other:thing': 'x'}) == {'ruleValid': 'T'}


class TestParseSubject:
    """Separators as in SubjectFinder.findByPackedSubjectString."""

    @pytest.mark.parametrize('packed, expected', [
        ('g:gsa :::: abc123', ('g:gsa', 'id', 'abc123')),
        (':::: abc123', (None, 'id', 'abc123')),
        ('ldap :::::: jdoe', ('ldap', 'identifier', 'jdoe')),
        (':::::: jdoe', (None, 'identifier', 'jdoe')),
        ('ldap :::::::: jdoe', ('ldap', 'id_or_identifier', 'jdoe')),
        ('jdoe', (None, 'id_or_identifier', 'jdoe')),
    ])
    def test_forms(self, packed, expected):
        assert rs.parse_subject(packed) == expected

    def test_matches_by_id(self):
        assert rs.subject_matches('g:gsa :::: abc123', SUBJECT)
        assert rs.subject_matches(':::: abc123', SUBJECT)
        assert not rs.subject_matches('ldap :::: abc123', SUBJECT)
        assert not rs.subject_matches('g:gsa :::: other', SUBJECT)

    def test_identifier_needs_the_task_identifier(self):
        assert not rs.subject_matches('g:gsa :::::: a:b', SUBJECT)
        assert rs.subject_matches('g:gsa :::::: a:b', SUBJECT, identifier='a:b')

    def test_pack_like_rule_api(self):
        assert rs.pack_subject(SUBJECT) == 'g:gsa :::: abc123'


class TestMatchingRules:

    def test_finds_the_subjects_rule_for_the_object_type(self):
        rules = [({'id': '1'}, group_rule()),
                 ({'id': '2'}, group_rule(arg0='g:gsa :::: someone')),
                 ({'id': '3'}, dict(group_rule(), ruleCheckType='stemCreate',
                                    ruleThenEnum='assignStemPrivilegeToStemId'))]
        found = rs.matching_rules(rules, 'group', SUBJECT, None)
        assert [marker['id'] for marker, unused in found] == ['1']
        found = rs.matching_rules(rules, 'folder', SUBJECT, None)
        assert [marker['id'] for marker, unused in found] == ['3']

    def test_scope_is_not_part_of_identity(self):
        rules = [({'id': '1'}, group_rule(scope='ONE'))]
        assert rs.matching_rules(rules, 'group', SUBJECT, None)

    def test_name_pattern_is_part_of_identity(self):
        patterned = group_rule(ruleIfConditionEnum=rs.NAME_MATCHES,
                               ruleIfConditionEnumArg0='a:%')
        rules = [({'id': '1'}, group_rule()), ({'id': '2'}, patterned)]
        assert [m['id'] for m, unused in
                rs.matching_rules(rules, 'group', SUBJECT, None)] == ['1']
        assert [m['id'] for m, unused in
                rs.matching_rules(rules, 'group', SUBJECT, 'a:%')] == ['2']

    def test_other_conditions_are_not_ours(self):
        rules = [({'id': '1'}, group_rule(ruleIfConditionEnum='somethingElse'))]
        assert rs.matching_rules(rules, 'group', SUBJECT, None) == []

    def test_duplicates_are_all_returned(self):
        rules = [({'id': '1'}, group_rule()), ({'id': '2'}, group_rule())]
        assert len(rs.matching_rules(rules, 'group', SUBJECT, None)) == 2
        message = rs.duplicate_message('a:b', 'group', [m for m, unused in rules])
        assert '1, 2' in message and 'a:b' in message


class TestPlanRule:

    def test_new_rule_is_written_whole_like_rule_api(self):
        desired, to_write = rs.plan_rule(None, 'group', SUBJECT, 'SUB',
                                         {'view', 'read'}, None)
        assert to_write == desired
        assert to_write == {
            rs.ACT_AS_SOURCE_ID: 'g:isa',
            rs.ACT_AS_SUBJECT_ID: 'GrouperSystem',
            rs.CHECK_TYPE: 'groupCreate',
            rs.CHECK_STEM_SCOPE: 'SUB',
            rs.THEN_ENUM: 'assignGroupPrivilegeToGroupId',
            rs.THEN_ARG0: 'g:gsa :::: abc123',
            rs.THEN_ARG1: 'read, view',
        }

    @pytest.mark.parametrize('object_type, check, then', [
        ('folder', 'stemCreate', 'assignStemPrivilegeToStemId'),
        ('attribute_def', 'attributeDefCreate',
         'assignAttributeDefPrivilegeToAttributeDefId'),
    ])
    def test_enums_per_object_type(self, object_type, check, then):
        desired, unused = rs.plan_rule(None, object_type, SUBJECT, 'ONE',
                                       {'x'}, None)
        assert desired[rs.CHECK_TYPE] == check
        assert desired[rs.THEN_ENUM] == then

    def test_new_rule_with_pattern(self):
        unused, to_write = rs.plan_rule(None, 'group', SUBJECT, 'SUB', {'read'}, 'a:%')
        assert to_write[rs.IF_CONDITION_ENUM] == 'nameMatchesSqlLikeString'
        assert to_write[rs.IF_CONDITION_ARG0] == 'a:%'

    def test_unchanged_rule_compares_privileges_as_a_set(self):
        unused, to_write = rs.plan_rule(group_rule(privileges='view,read'), 'group',
                                        SUBJECT, 'SUB', {'read', 'view'}, None)
        assert to_write == {}

    def test_scope_change_updates_in_place(self):
        unused, to_write = rs.plan_rule(group_rule(scope='ONE'), 'group',
                                        SUBJECT, 'SUB', {'read', 'view'}, None)
        assert to_write == {rs.CHECK_STEM_SCOPE: 'SUB'}

    def test_privilege_change_rewrites_only_the_list(self):
        unused, to_write = rs.plan_rule(group_rule(), 'group', SUBJECT, 'SUB',
                                        {'read'}, None)
        assert to_write == {rs.THEN_ARG1: 'read'}

    def test_legacy_stem_privilege_name_matches_stem_admin(self):
        current = dict(group_rule(privileges='stem, create'),
                       ruleCheckType='stemCreate')
        unused, to_write = rs.plan_rule(current, 'folder', SUBJECT, 'SUB',
                                        {'stemAdmin', 'create'}, None)
        assert to_write == {}

    def test_summary(self):
        assert rs.summary(group_rule(scope='ONE')) == {
            'scope': 'one', 'privileges': ['read', 'view']}
        assert rs.summary(None) == {}

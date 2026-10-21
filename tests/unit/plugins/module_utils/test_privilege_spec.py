# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.grouper.ws.plugins.module_utils import privilege_spec as ps

SUBJECT = {'id': 'GrouperAll', 'sourceId': 'g:isa'}


def membership(list_name, subject_id='GrouperAll', source='g:isa', kind='immediate'):
    return {'listName': list_name, 'subjectId': subject_id,
            'subjectSourceId': source, 'membershipType': kind}


class TestNames:
    """Names are taken verbatim from NamingPrivilege, AccessPrivilege and
    AttributeDefPrivilege."""

    def test_folder_names(self):
        wanted, problems = ps.to_grouper(
            ['admin', 'create', 'attr_read', 'attr_update', 'view'], 'stem')
        assert problems == []
        assert wanted == {'stemAdmin', 'create', 'stemAttrRead',
                          'stemAttrUpdate', 'stemView'}

    def test_group_names(self):
        wanted, problems = ps.to_grouper(
            ['admin', 'update', 'read', 'view', 'optin', 'optout',
             'attr_read', 'attr_update'], 'group')
        assert problems == []
        assert wanted == {'admin', 'update', 'read', 'view', 'optin', 'optout',
                          'groupAttrRead', 'groupAttrUpdate'}

    def test_attribute_def_names(self):
        wanted, unused = ps.to_grouper(['admin', 'attr_update'], 'attribute_def')
        assert wanted == {'attrAdmin', 'attrDefAttrUpdate'}

    def test_there_is_no_member_privilege(self):
        assert 'member' not in ps.all_names()

    @pytest.mark.parametrize('name', ['read', 'update', 'optin', 'optout'])
    def test_group_only_names_are_rejected_on_a_stem(self, name):
        wanted, problems = ps.to_grouper([name], 'stem')
        assert wanted == set()
        assert len(problems) == 1
        assert name in problems[0] and 'stem' in problems[0]

    def test_create_is_rejected_on_a_group(self):
        assert ps.to_grouper(['create'], 'group')[1]

    def test_back_to_friendly_names_sorted(self):
        assert ps.to_friendly({'stemView', 'stemAdmin'}, 'stem') == ['admin', 'view']

    def test_legacy_stem_name_reads_as_admin(self):
        assert ps.to_friendly({'stem'}, 'stem') == ['admin']


class TestImmediatePrivileges:

    def test_lists_map_to_privileges(self):
        held = ps.immediate_privileges(
            [membership('readers'), membership('groupAttrReaders')], SUBJECT)
        assert held == {'read', 'groupAttrRead'}

    def test_stem_lists_including_legacy_stemmers(self):
        held = ps.immediate_privileges(
            [membership('stemmers'), membership('creators'),
             membership('stemViewers')], SUBJECT)
        assert held == {'stemAdmin', 'create', 'stemView'}

    def test_effective_memberships_are_ignored(self):
        assert ps.immediate_privileges(
            [membership('admins', kind='effective')], SUBJECT) == set()

    def test_other_subjects_are_ignored(self):
        assert ps.immediate_privileges(
            [membership('admins', subject_id='someone')], SUBJECT) == set()
        assert ps.immediate_privileges(
            [membership('admins', source='ldap')], SUBJECT) == set()

    def test_non_privilege_lists_are_ignored(self):
        assert ps.immediate_privileges([membership('members')], SUBJECT) == set()

    def test_none(self):
        assert ps.immediate_privileges(None, SUBJECT) == set()


class TestPlan:

    def test_exact_set(self):
        assert ps.plan({'read', 'view'}, {'view', 'optin'}) == (['read'], ['optin'])

    def test_nothing_to_do(self):
        assert ps.plan({'read'}, {'read'}) == ([], [])

    def test_empty_revokes_everything(self):
        assert ps.plan(set(), {'admin', 'read'}) == ([], ['admin', 'read'])


class TestResultCodes:

    def test_codes_by_privilege(self):
        envelope = {'results': [
            {'privilegeName': 'read',
             'resultMetadata': {'resultCode': 'SUCCESS_ALLOWED'}},
            {'privilegeName': 'stem',
             'resultMetadata': {'resultCode': 'SUCCESS_ALLOWED_ALREADY_EXISTED'}},
        ]}
        assert ps.result_codes(envelope) == {
            'read': 'SUCCESS_ALLOWED',
            'stemAdmin': 'SUCCESS_ALLOWED_ALREADY_EXISTED',
        }

    def test_change_codes(self):
        assert 'SUCCESS_ALLOWED_ALREADY_EXISTED' not in ps.GRANTED_CODES
        assert 'SUCCESS_NOT_ALLOWED_DIDNT_EXIST' not in ps.REVOKED_CODES
        assert 'SUCCESS_NOT_ALLOWED_EXISTS_EFFECTIVE' in ps.REVOKED_CODES
        assert 'SUCCESS_NOT_ALLOWED_EXISTS_EFFECTIVE' in ps.STILL_EFFECTIVE_CODES

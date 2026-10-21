# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.grouper.ws.plugins.module_utils.marker_assign import (
    build_batch,
    find_markers,
    read_all,
)

SQL = 'etc:legacy:attribute:legacyGroupType_grouperLoader'
LDAP = 'etc:attribute:loaderLdap:grouperLoaderLdap'
JEXL = 'etc:attribute:abacJexlScript:grouperJexlScriptMarker'
RULE = 'etc:attribute:rules:rule'
ARG1 = 'etc:attribute:rules:ruleThenEnumArg1'


class FakeClient:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []

    def post(self, resource, request_name, body):
        self.calls.append((resource, request_name, body))
        return self.envelope


class TestFindMarkers:

    def test_one_call_looks_up_every_marker(self):
        client = FakeClient({'wsAttributeAssigns': []})
        assert find_markers(client, 'a:b', [SQL, LDAP]) == []
        assert len(client.calls) == 1
        body = client.calls[0][2]
        assert body['wsAttributeDefNameLookups'] == [{'name': SQL}, {'name': LDAP}]
        assert body['wsOwnerGroupLookups'] == [{'groupName': 'a:b'}]

    def test_reports_markers_on_this_group_in_request_order(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'L', 'attributeAssignType': 'group',
             'attributeDefNameName': LDAP, 'ownerGroupName': 'a:b'},
            {'id': 'S', 'attributeAssignType': 'group',
             'attributeDefNameName': SQL, 'ownerGroupName': 'a:b'},
        ]})
        assert find_markers(client, 'a:b', [SQL, LDAP]) == [SQL, LDAP]

    def test_markers_on_other_groups_are_ignored(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'S', 'attributeAssignType': 'group',
             'attributeDefNameName': SQL, 'ownerGroupName': 'other:group'},
        ]})
        assert find_markers(client, 'a:b', [SQL]) == []

    def test_assignments_on_assignments_are_not_markers(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'S', 'attributeAssignType': 'group_asgn',
             'attributeDefNameName': SQL, 'ownerGroupName': 'a:b'},
        ]})
        assert find_markers(client, 'a:b', [SQL]) == []

    def test_unrequested_markers_are_ignored(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'J', 'attributeAssignType': 'group',
             'attributeDefNameName': JEXL, 'ownerGroupName': 'a:b'},
        ]})
        assert find_markers(client, 'a:b', [SQL, LDAP]) == []


class TestStemOwners:

    def test_read_all_returns_every_marker_with_its_settings(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'R1', 'attributeAssignType': 'stem',
             'attributeDefNameName': RULE, 'ownerStemName': 'a:b'},
            {'id': 'R2', 'attributeAssignType': 'stem',
             'attributeDefNameName': RULE, 'ownerStemName': 'a:b'},
            {'id': 'S1', 'attributeAssignType': 'stem_asgn',
             'ownerAttributeAssignId': 'R1', 'attributeDefNameName': ARG1,
             'wsAttributeAssignValues': [{'valueSystem': 'read'}]},
            {'id': 'S2', 'attributeAssignType': 'stem_asgn',
             'ownerAttributeAssignId': 'R2', 'attributeDefNameName': ARG1,
             'wsAttributeAssignValues': [{'valueSystem': 'admin'}]},
            {'id': 'X', 'attributeAssignType': 'stem',
             'attributeDefNameName': RULE, 'ownerStemName': 'other'},
        ]})
        found = read_all(client, 'a:b', RULE)
        assert [(marker['id'], values) for marker, values in found] == [
            ('R1', {ARG1: 'read'}), ('R2', {ARG1: 'admin'})]
        body = client.calls[0][2]
        assert body['attributeAssignType'] == 'stem'
        assert body['wsOwnerStemLookups'] == [{'stemName': 'a:b'}]
        assert body['includeAssignmentsOnAssignments'] == 'T'

    def test_new_marker_on_a_stem_is_added_not_assigned(self):
        entries = build_batch('a:b', RULE, {ARG1: 'read'}, [], owner_type='stem',
                              add_new=True)
        assert entries[0] == {
            'wsOwnerStemLookup': {'stemName': 'a:b'},
            'attributeAssignType': 'stem',
            'attributeAssignOperation': 'add_attr',
            'wsAttributeDefNameLookup': {'name': RULE},
        }
        assert entries[1]['attributeAssignType'] == 'stem_asgn'
        assert entries[1]['wsOwnerAttributeAssignLookup'] == {'batchIndex': '0'}

    def test_existing_marker_is_referenced_by_uuid(self):
        entries = build_batch('a:b', RULE, {ARG1: 'read'}, [], owner_type='stem',
                              existing_id='R1')
        assert len(entries) == 1
        assert entries[0]['wsOwnerAttributeAssignLookup'] == {'uuid': 'R1'}
        assert entries[0]['values'] == [{'valueSystem': 'read'}]

    def test_group_default_is_unchanged(self):
        entries = build_batch('a:b', SQL, {ARG1: 'x'}, [ARG1 + 'z'])
        assert entries[0]['wsOwnerGroupLookup'] == {'groupName': 'a:b'}
        assert entries[0]['attributeAssignOperation'] == 'assign_attr'
        assert [e['attributeAssignType'] for e in entries[1:]] == ['group_asgn'] * 2
        assert entries[2]['attributeAssignOperation'] == 'remove_attr'

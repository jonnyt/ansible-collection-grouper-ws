# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.grouper.ws.plugins.modules.loader import (
    build_batch,
    read_current,
)

MARKER = 'etc:legacy:attribute:legacyGroupType_grouperLoader'
QUERY = 'etc:legacy:attribute:legacyAttribute_grouperLoaderQuery'
TYPE = 'etc:legacy:attribute:legacyAttribute_grouperLoaderType'


class FakeClient:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []

    def post(self, resource, request_name, body):
        self.calls.append((resource, request_name, body))
        return self.envelope


class TestReadCurrent:
    """Loader settings hang off the marker assignment, not off the group."""

    def test_no_marker_means_no_loader(self):
        client = FakeClient({'wsAttributeAssigns': []})
        marker, values = read_current(client, 'a:b', MARKER)
        assert marker is None
        assert values == {}

    def test_settings_are_matched_by_owner_assignment_id(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'M1', 'attributeAssignType': 'group',
             'attributeDefNameName': MARKER, 'ownerGroupName': 'a:b'},
            {'id': 'V1', 'attributeAssignType': 'group_asgn',
             'attributeDefNameName': QUERY, 'ownerAttributeAssignId': 'M1',
             'wsAttributeAssignValues': [{'valueSystem': 'select 1'}]},
            {'id': 'V2', 'attributeAssignType': 'group_asgn',
             'attributeDefNameName': TYPE, 'ownerAttributeAssignId': 'M1',
             'wsAttributeAssignValues': [{'valueSystem': 'SQL_SIMPLE'}]},
        ]})
        marker, values = read_current(client, 'a:b', MARKER)
        assert marker['id'] == 'M1'
        assert values == {QUERY: 'select 1', TYPE: 'SQL_SIMPLE'}

    def test_assignments_owned_by_something_else_are_ignored(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'M1', 'attributeAssignType': 'group',
             'attributeDefNameName': MARKER, 'ownerGroupName': 'a:b'},
            {'id': 'V9', 'attributeAssignType': 'group_asgn',
             'attributeDefNameName': QUERY, 'ownerAttributeAssignId': 'OTHER',
             'wsAttributeAssignValues': [{'valueSystem': 'nope'}]},
        ]})
        unused_marker, values = read_current(client, 'a:b', MARKER)
        assert values == {}

    def test_marker_for_another_group_is_ignored(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'M1', 'attributeAssignType': 'group',
             'attributeDefNameName': MARKER, 'ownerGroupName': 'other:group'},
        ]})
        marker, unused_values = read_current(client, 'a:b', MARKER)
        assert marker is None

    def test_valueless_assignment_reads_as_empty_string(self):
        client = FakeClient({'wsAttributeAssigns': [
            {'id': 'M1', 'attributeAssignType': 'group',
             'attributeDefNameName': MARKER, 'ownerGroupName': 'a:b'},
            {'id': 'V1', 'attributeAssignType': 'group_asgn',
             'attributeDefNameName': QUERY, 'ownerAttributeAssignId': 'M1'},
        ]})
        unused_marker, values = read_current(client, 'a:b', MARKER)
        assert values == {QUERY: ''}


class TestBuildBatch:

    def test_marker_is_entry_zero_and_settings_reference_it(self):
        entries = build_batch('a:b', MARKER, {QUERY: 'select 1'}, [])
        assert entries[0] == {
            'wsOwnerGroupLookup': {'groupName': 'a:b'},
            'attributeAssignType': 'group',
            'attributeAssignOperation': 'assign_attr',
            'wsAttributeDefNameLookup': {'name': MARKER},
        }
        assert entries[1]['wsOwnerAttributeAssignLookup'] == {'batchIndex': '0'}
        assert entries[1]['attributeAssignType'] == 'group_asgn'
        assert entries[1]['values'] == [{'valueSystem': 'select 1'}]
        assert entries[1]['attributeAssignValueOperation'] == 'replace_values'

    def test_removals_use_remove_attr(self):
        entries = build_batch('a:b', MARKER, {}, [QUERY])
        assert len(entries) == 2
        assert entries[1]['attributeAssignOperation'] == 'remove_attr'
        assert entries[1]['wsAttributeDefNameLookup'] == {'name': QUERY}
        assert 'values' not in entries[1]

    def test_only_the_marker_when_nothing_differs(self):
        assert len(build_batch('a:b', MARKER, {}, [])) == 1

    def test_entries_are_deterministically_ordered(self):
        entries = build_batch('a:b', MARKER, {QUERY: 'q', TYPE: 't'}, [])
        names = [e['wsAttributeDefNameLookup']['name'] for e in entries[1:]]
        assert names == sorted(names)

# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible_collections.grouper.ws.plugins.module_utils.marker_assign import (
    find_markers,
)

SQL = 'etc:legacy:attribute:legacyGroupType_grouperLoader'
LDAP = 'etc:attribute:loaderLdap:grouperLoaderLdap'
JEXL = 'etc:attribute:abacJexlScript:grouperJexlScriptMarker'


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

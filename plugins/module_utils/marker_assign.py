# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Read and write settings that hang off a marker assignment on a group.

SQL loaders, LDAP loaders and JEXL scripted groups all share one shape: a
marker attribute is assigned to the group, and every individual setting is
assigned *on that marker assignment* (attributeAssignType ``group_asgn``).
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type


def _group_markers(assigns, group, marker_names):
    """Return {marker name: assignment} for markers assigned to the group."""
    found = {}
    for assign in assigns:
        name = assign.get('attributeDefNameName')
        if (assign.get('attributeAssignType') == 'group'
                and name in marker_names
                and assign.get('ownerGroupName') == group
                and name not in found):
            found[name] = assign
    return found


def find_markers(client, group, marker_names):
    """Return the subset of marker_names assigned directly to the group.

    One round trip, so a module can check for conflicting markers before it
    reads or writes anything.
    """
    marker_names = list(marker_names)
    envelope = client.post(
        'attributeAssignments', 'WsRestGetAttributeAssignmentsRequest', {
            'attributeAssignType': 'group',
            'wsOwnerGroupLookups': [{'groupName': group}],
            'wsAttributeDefNameLookups': [{'name': name} for name in marker_names],
        })
    found = _group_markers(envelope.get('wsAttributeAssigns') or [],
                           group, marker_names)
    return [name for name in marker_names if name in found]


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

    marker = _group_markers(assigns, group, [marker_name]).get(marker_name)
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
    it by batchIndex, so a brand new marker and an update to an existing one
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

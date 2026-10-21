# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Read and write settings that hang off a marker assignment.

SQL loaders, LDAP loaders and JEXL scripted groups all share one shape: a
marker attribute is assigned to the group, and every individual setting is
assigned *on that marker assignment* (attributeAssignType ``group_asgn``).
Grouper rules, which carry inherited privileges, take the same shape on a stem
(``stem`` / ``stem_asgn``), except that a stem may hold many rule markers.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type


#: Per owner type: (lookup key, plural lookup key, name field, owner name field).
OWNERS = {
    'group': ('wsOwnerGroupLookup', 'wsOwnerGroupLookups', 'groupName',
              'ownerGroupName'),
    'stem': ('wsOwnerStemLookup', 'wsOwnerStemLookups', 'stemName',
             'ownerStemName'),
}


def _owner_markers(assigns, owner, marker_names, owner_type='group'):
    """Return every assignment of the named markers directly on the owner."""
    owner_field = OWNERS[owner_type][3]
    return [assign for assign in assigns
            if assign.get('attributeAssignType') == owner_type
            and assign.get('attributeDefNameName') in marker_names
            and assign.get(owner_field) == owner]


def _group_markers(assigns, group, marker_names):
    """Return {marker name: assignment} for markers assigned to the group."""
    found = {}
    for assign in _owner_markers(assigns, group, marker_names):
        found.setdefault(assign.get('attributeDefNameName'), assign)
    return found


def _settings_of(assigns, marker):
    """Return {attribute def name: value} for settings on one marker assignment."""
    values = {}
    for assign in assigns:
        if assign.get('ownerAttributeAssignId') != marker.get('id'):
            continue
        name = assign.get('attributeDefNameName')
        if not name:
            continue
        assign_values = assign.get('wsAttributeAssignValues') or []
        values[name] = assign_values[0].get('valueSystem', '') if assign_values else ''
    return values


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
    return marker, _settings_of(assigns, marker)


def read_all(client, owner, marker_name, owner_type='stem'):
    """Return [(marker assignment, {attribute def name: value})] on the owner.

    For markers that may be assigned many times over, such as Grouper rules.
    One round trip returns every marker with the settings on each.
    """
    lookup, lookups, name_field = OWNERS[owner_type][:3]
    envelope = client.post(
        'attributeAssignments', 'WsRestGetAttributeAssignmentsRequest', {
            'attributeAssignType': owner_type,
            lookups: [{name_field: owner}],
            'wsAttributeDefNameLookups': [{'name': marker_name}],
            'includeAssignmentsOnAssignments': 'T',
        })
    assigns = envelope.get('wsAttributeAssigns') or []
    return [(marker, _settings_of(assigns, marker))
            for marker in _owner_markers(assigns, owner, [marker_name], owner_type)]


def build_batch(owner, marker_name, to_write, to_remove, owner_type='group',
                existing_id=None, add_new=False):
    """Build assignAttributesBatch entries.

    Entry 0 assigns the marker to the owner and every other entry references
    it by batchIndex, so a brand new marker and an update to an existing one
    take exactly the same shape and a single round trip.

    A marker that may be assigned many times over (a stem's rules) cannot work
    that way, since assign_attr would land on whichever one exists. For those,
    an existing marker is named by ``existing_id`` and the settings reference
    it directly, and ``add_new`` creates another with add_attr.
    """
    if existing_id:
        entries = []
        marker_ref = {'uuid': existing_id}
    else:
        lookup, unused_lookups, name_field = OWNERS[owner_type][:3]
        entries = [{
            lookup: {name_field: owner},
            'attributeAssignType': owner_type,
            'attributeAssignOperation': 'add_attr' if add_new else 'assign_attr',
            'wsAttributeDefNameLookup': {'name': marker_name},
        }]
        marker_ref = {'batchIndex': '0'}

    asgn_type = '%s_asgn' % owner_type
    for name in sorted(to_write):
        entries.append({
            'wsOwnerAttributeAssignLookup': marker_ref,
            'attributeAssignType': asgn_type,
            'attributeAssignOperation': 'assign_attr',
            'wsAttributeDefNameLookup': {'name': name},
            'attributeAssignValueOperation': 'replace_values',
            'values': [{'valueSystem': to_write[name]}],
        })

    for name in sorted(to_remove):
        entries.append({
            'wsOwnerAttributeAssignLookup': marker_ref,
            'attributeAssignType': asgn_type,
            'attributeAssignOperation': 'remove_attr',
            'wsAttributeDefNameLookup': {'name': name},
        })

    return entries

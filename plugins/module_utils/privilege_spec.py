# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""Grouper privilege names, and how privilege grants map onto Grouper.

Names come from ``NamingPrivilege.java`` (folders), ``AccessPrivilege.java``
(groups) and ``AttributeDefPrivilege.java`` (attribute defs). There is no
"member" privilege: membership is not a privilege, and this collection never
manages it.

Each privilege is stored as an immediate membership of a privilege list on
the owner, for example ``readers`` on a group. Reading those lists through
getMemberships with ``memberFilter: Immediate`` is the reliable way to see what
was granted directly. The ``revokable`` flag on getGrouperPrivilegesLite looks
like it should answer the same question, but ``GrouperPrivilegeAdapter`` carries
it across loop iterations without resetting it, and on 6.5.0 it reports ``F``
for privileges granted directly to GrouperAll.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

#: Task-facing privilege names per owner type, mapped to Grouper's names.
PRIVILEGES = {
    'stem': {
        'admin': 'stemAdmin',
        'create': 'create',
        'attr_read': 'stemAttrRead',
        'attr_update': 'stemAttrUpdate',
        'view': 'stemView',
    },
    'group': {
        'admin': 'admin',
        'update': 'update',
        'read': 'read',
        'view': 'view',
        'optin': 'optin',
        'optout': 'optout',
        'attr_read': 'groupAttrRead',
        'attr_update': 'groupAttrUpdate',
    },
    'attribute_def': {
        'admin': 'attrAdmin',
        'update': 'attrUpdate',
        'read': 'attrRead',
        'view': 'attrView',
        'optin': 'attrOptin',
        'optout': 'attrOptout',
        'attr_read': 'attrDefAttrRead',
        'attr_update': 'attrDefAttrUpdate',
    },
}

#: privilegeType for assignGrouperPrivileges, which handles stems and groups only.
PRIVILEGE_TYPES = {'stem': 'naming', 'group': 'access'}

#: Older Grouper names still accepted and returned for stem admin.
ALIASES = {'stem': 'stemAdmin'}

#: Privilege list names from Field.java, mapped to Grouper privilege names.
LIST_PRIVILEGES = {
    'admins': 'admin',
    'updaters': 'update',
    'readers': 'read',
    'viewers': 'view',
    'optins': 'optin',
    'optouts': 'optout',
    'groupAttrReaders': 'groupAttrRead',
    'groupAttrUpdaters': 'groupAttrUpdate',
    'stemAdmins': 'stemAdmin',
    'stemmers': 'stemAdmin',
    'creators': 'create',
    'stemAttrReaders': 'stemAttrRead',
    'stemAttrUpdaters': 'stemAttrUpdate',
    'stemViewers': 'stemView',
}

#: Per-item assignGrouperPrivileges codes that mean Grouper wrote something.
GRANTED_CODES = frozenset(['SUCCESS_ALLOWED'])
REVOKED_CODES = frozenset(['SUCCESS_NOT_ALLOWED', 'SUCCESS_NOT_ALLOWED_EXISTS_EFFECTIVE'])
#: Revoke codes meaning the subject still holds the privilege through a group.
STILL_EFFECTIVE_CODES = frozenset([
    'SUCCESS_NOT_ALLOWED_EXISTS_EFFECTIVE',
    'SUCCESS_NOT_ALLOWED_DIDNT_EXIST_BUT_EXISTS_EFFECTIVE',
])


def all_names():
    """Every task-facing privilege name, for an argument spec's choices."""
    names = set()
    for mapping in PRIVILEGES.values():
        names.update(mapping)
    return sorted(names)


def to_grouper(names, owner_type):
    """Return (Grouper names, problems) for task-facing names on an owner type."""
    mapping = PRIVILEGES[owner_type]
    wanted = set()
    unknown = []
    for name in names or []:
        if name in mapping:
            wanted.add(mapping[name])
        else:
            unknown.append(name)
    problems = []
    if unknown:
        problems.append('%s not valid on a %s; choose from %s'
                        % (', '.join(sorted(set(unknown))),
                           owner_type.replace('_', ' '),
                           ', '.join(sorted(mapping))))
    return wanted, problems


def to_friendly(grouper_names, owner_type):
    """Map Grouper names back to task-facing names, sorted, for return values."""
    reverse = dict((v, k) for k, v in PRIVILEGES[owner_type].items())
    return sorted(reverse.get(normalise(name), name) for name in grouper_names)


def normalise(name):
    name = (name or '').strip()
    return ALIASES.get(name, name)


def immediate_privileges(memberships, subject):
    """Grouper names the subject holds directly, from getMemberships results."""
    held = set()
    for membership in memberships or []:
        if (membership.get('membershipType') or 'immediate') != 'immediate':
            continue
        if membership.get('subjectId') != subject.get('id'):
            continue
        if (membership.get('subjectSourceId')
                and membership.get('subjectSourceId') != subject.get('sourceId')):
            continue
        privilege = LIST_PRIVILEGES.get(membership.get('listName'))
        if privilege:
            held.add(privilege)
    return held


def plan(wanted, held):
    """Return sorted (to_grant, to_revoke) making held exactly wanted."""
    return sorted(set(wanted) - set(held)), sorted(set(held) - set(wanted))


def result_codes(envelope):
    """Return {privilege name: per-item result code} from an assign response."""
    codes = {}
    for result in envelope.get('results') or []:
        meta = result.get('resultMetadata') or {}
        codes[normalise(result.get('privilegeName'))] = meta.get('resultCode')
    return codes

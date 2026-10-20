# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""How Grouper JEXL scripted (ABAC) groups map onto attributes.

The group carries the marker
``etc:attribute:abacJexlScript:grouperJexlScriptMarker``, and the script and
optional subject source ids are attributes assigned *on that marker
assignment*, the same shape as an LDAP loader.

The names below come from ``GrouperAbac.java`` and the attribute defs from
``GrouperCheckConfig.java``. The stem is built from
``grouper.rootStemForBuiltinObjects``, not from ``grouper.attribute.rootStem``
as LDAP loaders are, so it is overridden separately.

These groups are not a ``GrouperLoaderType``. They are run by
``GrouperLoaderJexlScriptIncremental``, a change log consumer that recalculates
a group whenever its script or source id value changes, and by the daily
``GrouperLoaderJexlScriptFullSync``, which scans every marker. Nothing needs
scheduling after a write.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DEFAULT_JEXL_SCRIPT_STEM = 'etc:attribute:abacJexlScript'

MARKER_EXTENSION = 'grouperJexlScriptMarker'
SCRIPT_EXTENSION = 'grouperJexlScriptJexlScript'
SUBJECT_SOURCE_IDS_EXTENSION = 'grouperJexlScriptSubjectSourceIds'
# Written by the daemons after each group sync. Never managed here.
LAST_GROUP_SYNC_EXTENSION = 'grouperJexlScriptJexlLastGroupSync'


class JexlNaming(object):
    """Resolves fully qualified attribute names under the JEXL script stem."""

    def __init__(self, jexl_script_stem=None):
        self.stem = (jexl_script_stem or DEFAULT_JEXL_SCRIPT_STEM).rstrip(':')

    def attribute_name(self, extension):
        return '%s:%s' % (self.stem, extension)

    @property
    def marker_name(self):
        return self.attribute_name(MARKER_EXTENSION)

    @property
    def script_name(self):
        return self.attribute_name(SCRIPT_EXTENSION)

    @property
    def subject_source_ids_name(self):
        return self.attribute_name(SUBJECT_SOURCE_IDS_EXTENSION)


def validate_script(script):
    """Return a list of problems with the script, empty when it is usable.

    Grouper itself checks almost nothing: GrouperAbac.validScript() returns
    early, and the daemons accept the script with or without its ${...}
    wrapper. A blank script is the one thing the UI refuses.
    """
    if script is None or not script.strip():
        return ['script must not be blank']
    return []


def normalise_source_ids(value):
    """Render source ids the way the UI stores them: sorted, unique, ', ' joined.

    Accepts a list or the stored comma separated string, so a value typed in
    by hand compares equal to the same set declared in a task.
    """
    if value is None:
        return ''
    if not isinstance(value, (list, tuple)):
        value = value.split(',')
    ids = sorted(set(item.strip() for item in value if item and item.strip()))
    return ', '.join(ids)


def plan_changes(script, subject_source_ids, current, naming):
    """Return (desired, to_write, to_remove) for a JEXL script definition.

    ``subject_source_ids`` of None leaves the stored value alone; an empty
    list removes it, which Grouper reads as "use the global default sources",
    exactly what the UI does when the defaults are chosen.
    """
    desired = {naming.script_name: script.strip()}
    to_remove = []

    if subject_source_ids is not None:
        wanted = normalise_source_ids(subject_source_ids)
        name = naming.subject_source_ids_name
        if wanted:
            desired[name] = wanted
        elif name in current:
            to_remove.append(name)

    to_write = {}
    for name, value in desired.items():
        if name == naming.subject_source_ids_name:
            if normalise_source_ids(current.get(name)) == value and name in current:
                continue
        elif current.get(name) == value:
            continue
        to_write[name] = value

    return desired, to_write, to_remove


def conflict_message(group, loader_markers):
    """Explain why a group already driven by a loader cannot take a script."""
    return ('Group %s already has a loader definition (%s). A group is driven '
            'by one loader at a time, and this collection never removes a '
            'loader, so remove it in the Grouper UI first.'
            % (group, ', '.join(loader_markers)))

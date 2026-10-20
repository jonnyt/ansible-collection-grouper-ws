# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.grouper.ws.plugins.module_utils import jexl_spec as js

SCRIPT = 'etc:attribute:abacJexlScript:grouperJexlScriptJexlScript'
SOURCES = 'etc:attribute:abacJexlScript:grouperJexlScriptSubjectSourceIds'
LAST_SYNC = 'etc:attribute:abacJexlScript:grouperJexlScriptJexlLastGroupSync'
RULE = "${entity.memberOf('ref:staff')}"


class TestNaming:
    """Names are taken verbatim from GrouperAbac.java."""

    def test_default_names(self):
        naming = js.JexlNaming()
        assert naming.marker_name == \
            'etc:attribute:abacJexlScript:grouperJexlScriptMarker'
        assert naming.script_name == SCRIPT
        assert naming.subject_source_ids_name == SOURCES

    def test_custom_stem_is_honoured(self):
        naming = js.JexlNaming('custom:attribute:abacJexlScript:')
        assert naming.marker_name == \
            'custom:attribute:abacJexlScript:grouperJexlScriptMarker'


class TestValidateScript:

    @pytest.mark.parametrize('script', [None, '', '   \n'])
    def test_blank_is_rejected(self, script):
        assert js.validate_script(script) == ['script must not be blank']

    @pytest.mark.parametrize('script', [
        RULE,
        "entity.memberOf('ref:staff')",
        '${entity.memberOf("ref:staff")}',
    ])
    def test_grouper_accepts_any_non_blank_script(self, script):
        assert js.validate_script(script) == []


class TestNormaliseSourceIds:

    def test_sorted_unique_and_joined_like_the_ui(self):
        assert js.normalise_source_ids(['ldap', 'jdbc', 'ldap']) == 'jdbc, ldap'

    def test_hand_typed_string_normalises_to_the_same_value(self):
        assert js.normalise_source_ids(' ldap ,jdbc,') == 'jdbc, ldap'

    @pytest.mark.parametrize('value', [None, [], '', ' , '])
    def test_empty(self, value):
        assert js.normalise_source_ids(value) == ''


class TestPlanChanges:

    def setup_method(self):
        self.naming = js.JexlNaming()

    def test_new_script_is_written(self):
        desired, to_write, to_remove = js.plan_changes(RULE, None, {}, self.naming)
        assert desired == {SCRIPT: RULE}
        assert to_write == {SCRIPT: RULE}
        assert to_remove == []

    def test_script_is_trimmed_like_the_ui(self):
        unused_desired, to_write, unused_remove = js.plan_changes(
            '  %s\n' % RULE, None, {SCRIPT: RULE}, self.naming)
        assert to_write == {}

    def test_unchanged_script_writes_nothing(self):
        unused_desired, to_write, to_remove = js.plan_changes(
            RULE, None, {SCRIPT: RULE}, self.naming)
        assert to_write == {}
        assert to_remove == []

    def test_omitted_source_ids_are_left_alone(self):
        current = {SCRIPT: RULE, SOURCES: 'ldap'}
        desired, to_write, to_remove = js.plan_changes(RULE, None, current, self.naming)
        assert SOURCES not in desired
        assert to_write == {}
        assert to_remove == []

    def test_source_ids_are_written_normalised(self):
        unused_desired, to_write, unused_remove = js.plan_changes(
            RULE, ['ldap', 'jdbc'], {SCRIPT: RULE}, self.naming)
        assert to_write == {SOURCES: 'jdbc, ldap'}

    def test_equivalent_stored_source_ids_are_not_rewritten(self):
        current = {SCRIPT: RULE, SOURCES: 'ldap,jdbc'}
        unused_desired, to_write, unused_remove = js.plan_changes(
            RULE, ['jdbc', 'ldap'], current, self.naming)
        assert to_write == {}

    def test_empty_source_ids_remove_the_attribute(self):
        current = {SCRIPT: RULE, SOURCES: 'ldap'}
        desired, to_write, to_remove = js.plan_changes(RULE, [], current, self.naming)
        assert SOURCES not in desired
        assert to_write == {}
        assert to_remove == [SOURCES]

    def test_empty_source_ids_with_nothing_stored_is_a_no_op(self):
        unused_desired, to_write, to_remove = js.plan_changes(
            RULE, [], {SCRIPT: RULE}, self.naming)
        assert to_write == {}
        assert to_remove == []

    def test_daemon_sync_timestamp_is_never_touched(self):
        current = {SCRIPT: 'old', SOURCES: 'ldap', LAST_SYNC: '2026-01-01T00:00:00Z'}
        desired, to_write, to_remove = js.plan_changes(RULE, [], current, self.naming)
        assert LAST_SYNC not in desired
        assert LAST_SYNC not in to_write
        assert LAST_SYNC not in to_remove


def test_conflict_message_names_the_group_and_loader():
    msg = js.conflict_message('a:b', ['etc:legacy:attribute:legacyGroupType_grouperLoader'])
    assert 'a:b' in msg
    assert 'legacyGroupType_grouperLoader' in msg

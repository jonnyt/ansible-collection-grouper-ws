# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.grouper.ws.plugins.module_utils import loader_spec as ls


class TestNaming:
    """The attribute names below are taken verbatim from the Grouper source.

    SQL loaders live in the legacy attribute framework keyed off the
    grouperLoader group type; LDAP loaders live under etc:attribute:loaderLdap.
    Getting either wrong silently produces a loader Grouper will not run.
    """

    def test_sql_marker_is_the_legacy_group_type(self):
        naming = ls.LoaderNaming('SQL_GROUP_LIST')
        assert naming.marker_name == 'etc:legacy:attribute:legacyGroupType_grouperLoader'

    def test_sql_settings_use_the_legacy_attribute_prefix(self):
        naming = ls.LoaderNaming('SQL_SIMPLE')
        assert naming.attribute_name('grouperLoaderQuery') == \
            'etc:legacy:attribute:legacyAttribute_grouperLoaderQuery'
        assert naming.type_attribute_name == \
            'etc:legacy:attribute:legacyAttribute_grouperLoaderType'

    def test_ldap_marker_and_settings(self):
        naming = ls.LoaderNaming('LDAP_GROUP_LIST')
        assert naming.marker_name == 'etc:attribute:loaderLdap:grouperLoaderLdap'
        assert naming.attribute_name('grouperLoaderLdapFilter') == \
            'etc:attribute:loaderLdap:grouperLoaderLdapFilter'
        assert naming.type_attribute_name == \
            'etc:attribute:loaderLdap:grouperLoaderLdapType'

    def test_custom_root_stems_are_honoured(self):
        naming = ls.LoaderNaming(
            'LDAP_SIMPLE', attribute_root_stem='custom:attribute',
            legacy_attribute_stem='custom:legacy:attribute')
        assert naming.marker_name == 'custom:attribute:loaderLdap:grouperLoaderLdap'

        naming = ls.LoaderNaming(
            'SQL_SIMPLE', legacy_attribute_stem='custom:legacy:attribute')
        assert naming.marker_name == \
            'custom:legacy:attribute:legacyGroupType_grouperLoader'


class TestBuildDesiredAttributes:

    def test_type_is_always_written(self):
        naming = ls.LoaderNaming('SQL_SIMPLE')
        desired = ls.build_desired_attributes('SQL_SIMPLE', {}, naming)
        assert desired == {
            'etc:legacy:attribute:legacyAttribute_grouperLoaderType': 'SQL_SIMPLE',
        }

    def test_unset_options_are_not_managed(self):
        naming = ls.LoaderNaming('SQL_SIMPLE')
        desired = ls.build_desired_attributes(
            'SQL_SIMPLE', {'query': 'select 1', 'group_query': None}, naming)
        assert 'etc:legacy:attribute:legacyAttribute_grouperLoaderGroupQuery' \
            not in desired
        assert desired['etc:legacy:attribute:legacyAttribute_grouperLoaderQuery'] \
            == 'select 1'

    def test_lists_become_comma_separated_strings(self):
        naming = ls.LoaderNaming('SQL_GROUP_LIST')
        desired = ls.build_desired_attributes(
            'SQL_GROUP_LIST', {'and_groups': ['a:b', 'c:d']}, naming)
        assert desired['etc:legacy:attribute:legacyAttribute_grouperLoaderAndGroups'] \
            == 'a:b, c:d'

    def test_ints_become_strings(self):
        naming = ls.LoaderNaming('SQL_SIMPLE')
        desired = ls.build_desired_attributes(
            'SQL_SIMPLE', {'interval_seconds': 3600}, naming)
        value = desired[
            'etc:legacy:attribute:legacyAttribute_grouperLoaderIntervalSeconds']
        assert value == '3600'
        assert isinstance(value, str)


class TestValidateOptions:

    def test_valid_sql_group_list(self):
        assert ls.validate_options('SQL_GROUP_LIST', {
            'database': 'grouper',
            'query': 'select 1',
            'schedule_type': 'CRON',
            'quartz_cron': '0 0 7 * * ?',
            'group_query': 'select 1',
        }) == []

    def test_missing_required_is_reported(self):
        errors = ls.validate_options('SQL_SIMPLE', {'query': 'select 1'})
        assert any("'database' is required" in e for e in errors)
        assert any("'schedule_type' is required" in e for e in errors)

    def test_cron_schedule_requires_a_cron_expression(self):
        errors = ls.validate_options('SQL_SIMPLE', {
            'database': 'grouper', 'query': 'select 1', 'schedule_type': 'CRON',
        })
        assert any('requires' in e and 'quartz_cron' in e for e in errors)

    def test_interval_schedule_requires_an_interval(self):
        errors = ls.validate_options('SQL_SIMPLE', {
            'database': 'grouper', 'query': 'select 1',
            'schedule_type': 'START_TO_START_INTERVAL',
        })
        assert any('interval_seconds' in e for e in errors)

    def test_group_query_is_rejected_for_sql_simple(self):
        # group_query only makes sense when one job drives many groups.
        errors = ls.validate_options('SQL_SIMPLE', {
            'database': 'grouper', 'query': 'select 1',
            'schedule_type': 'START_TO_START_INTERVAL', 'interval_seconds': 60,
            'group_query': 'select 1',
        })
        assert any("'group_query' is not supported" in e for e in errors)

    def test_display_name_expression_rejected_for_ldap_simple(self):
        # Grouper's source marks the display expression "not allowed" here.
        errors = ls.validate_options('LDAP_SIMPLE', {
            'server_id': 'personLdap', 'filter': '(cn=x)',
            'quartz_cron': '0 0 * * * ?', 'subject_attribute': 'hasMember',
            'group_display_name_expression': '${x}',
        })
        assert any('group_display_name_expression' in e for e in errors)

    def test_display_name_expression_allowed_for_ldap_group_list(self):
        assert ls.validate_options('LDAP_GROUP_LIST', {
            'server_id': 'personLdap', 'filter': '(cn=x)',
            'quartz_cron': '0 0 * * * ?', 'subject_attribute': 'hasMember',
            'group_display_name_expression': '${x}',
        }) == []

    def test_groups_from_attributes_requires_group_attribute(self):
        errors = ls.validate_options('LDAP_GROUPS_FROM_ATTRIBUTES', {
            'server_id': 'personLdap', 'filter': '(cn=x)',
            'quartz_cron': '0 0 * * * ?',
        })
        assert any("'group_attribute' is required" in e for e in errors)


class TestSchemaConsistency:
    """Guards against the option maps and the allow lists drifting apart."""

    @pytest.mark.parametrize('loader_type', ls.LOADER_TYPES)
    def test_required_is_a_subset_of_allowed(self, loader_type):
        assert set(ls.REQUIRED_OPTIONS[loader_type]) <= \
            ls.ALLOWED_OPTIONS[loader_type]

    @pytest.mark.parametrize('loader_type', ls.LOADER_TYPES)
    def test_every_allowed_option_has_an_attribute_name(self, loader_type):
        option_map = (ls.SQL_ATTRIBUTE_MAP if ls.is_sql(loader_type)
                      else ls.LDAP_ATTRIBUTE_MAP)
        assert ls.ALLOWED_OPTIONS[loader_type] <= set(option_map)

    @pytest.mark.parametrize('loader_type', ls.LOADER_TYPES)
    def test_every_type_has_an_entry(self, loader_type):
        assert loader_type in ls.REQUIRED_OPTIONS
        assert loader_type in ls.ALLOWED_OPTIONS

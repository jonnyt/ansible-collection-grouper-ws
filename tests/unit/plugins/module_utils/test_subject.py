# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import pytest

from ansible_collections.grouper.ws.plugins.module_utils.grouper import (
    GrouperError,
    resolve_subject,
    subject_lookup,
)


class FakeClient:
    def __init__(self, envelope):
        self.envelope = envelope
        self.calls = []

    def post(self, resource, request_name, body):
        self.calls.append((resource, request_name, body))
        return self.envelope


def params(**given):
    base = dict(subject_id=None, subject_identifier=None,
                subject_source_id=None, subject_group=None)
    base.update(given)
    return base


class TestSubjectLookup:

    def test_group_is_an_identifier_in_g_gsa(self):
        assert subject_lookup(params(subject_group='a:b')) == {
            'subjectIdentifier': 'a:b', 'subjectSourceId': 'g:gsa'}

    def test_id_with_source(self):
        assert subject_lookup(params(subject_id='123', subject_source_id='ldap')) == {
            'subjectId': '123', 'subjectSourceId': 'ldap'}

    def test_identifier_alone(self):
        assert subject_lookup(params(subject_identifier='jdoe')) == {
            'subjectIdentifier': 'jdoe'}


class TestResolveSubject:

    def test_found(self):
        subject = {'success': 'T', 'resultCode': 'SUCCESS', 'id': 'GrouperAll',
                   'sourceId': 'g:isa'}
        client = FakeClient({'wsSubjects': [subject]})
        assert resolve_subject(client, {'subjectId': 'GrouperAll'}) == subject
        assert client.calls[0][:2] == ('subjects', 'WsRestGetSubjectsRequest')
        assert client.calls[0][2] == {'wsSubjectLookups': [{'subjectId': 'GrouperAll'}]}

    def test_not_found_names_the_subject(self):
        client = FakeClient({'wsSubjects': [
            {'success': 'F', 'resultCode': 'SUBJECT_NOT_FOUND', 'sourceId': 'g:gsa'}]})
        with pytest.raises(GrouperError) as exc:
            resolve_subject(client, {'subjectIdentifier': 'a:nope',
                                     'subjectSourceId': 'g:gsa'})
        assert 'a:nope in source g:gsa' in exc.value.message
        assert 'SUBJECT_NOT_FOUND' in exc.value.message

# -*- coding: utf-8 -*-
# Copyright (c) 2026 Jonathon Taylor
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  subject_id:
    description:
      - Id of the person or other subject the privileges are for.
      - Exactly one of I(subject_id), I(subject_identifier) and I(subject_group)
        is required.
    type: str
  subject_identifier:
    description:
      - Identifier of the subject, for example a login name.
    type: str
  subject_source_id:
    description:
      - Subject source to look I(subject_id) or I(subject_identifier) up in.
      - Recommended whenever more than one source could hold the subject.
    type: str
  subject_group:
    description:
      - Full colon delimited name of a group to give the privileges to, so
        that they apply to everyone in it.
      - Shorthand for I(subject_identifier) set to the group name in source
        C(g:gsa).
    type: str
'''

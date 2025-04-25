#  Copyright (c) 2025 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

DOCUMENTATION = r"""
name: utils
short_description: Attribute comparison filters for lists of dictionaries
version_added: 1.1.0
author:
  - Alexander Ursu (@aursu)
description:
  - Provides filters to compare attribute values across a list of dictionaries.
  - Useful in validating uniformity or detecting inconsistencies in structured data like inventory, facts, or custom inputs.
options:
  _input:
    description: A list of dictionaries to be checked.
    type: list
    elements: dict
    required: true
"""

RETURN = r"""
_value:
  description:
    - C(all_attr_equals) returns True if all dictionaries have the same value for a given attribute.
    - C(any_attr_not) returns True if any dictionary has a different value than expected.
  type: bool
"""

EXAMPLES = r"""
- name: Check if all items have the same state
  debug:
    msg: "{{ [{'state': 'ok'}, {'state': 'ok'}] | aursu.general.all_attr_equals('state', 'ok') }}"
  # Output: true

- name: Check if any item has a different type
  debug:
    msg: "{{ [{'type': 'primary'}, {'type': 'backup'}] | aursu.general.any_attr_not('type', 'primary') }}"
  # Output: true

- name: Edge case: empty list always returns true for all_attr_equals
  debug:
    msg: "{{ [] | aursu.general.all_attr_equals('status', 'ok') }}"
  # Output: true
"""

def all_attr_equals(data, attr, expected):
    """
    Check if all dictionaries in the list have the same value for a given attribute.

    Args:
        data (list): List of dictionaries.
        attr (str): Attribute to check.
        expected (any): Value to compare against.

    Returns:
        bool: True if all dicts have attr == expected.
    """
    return all(item.get(attr) == expected for item in data)

def any_attr_not(data, attr, expected):
    """
    Check if any dictionary has a different value for a given attribute.

    Args:
        data (list): List of dictionaries.
        attr (str): Attribute to check.
        expected (any): Value to compare against.

    Returns:
        bool: True if any dict has attr != expected.
    """
    return not all_attr_equals(data, attr, expected)

class FilterModule(object):
    def filters(self):
        return {
            "any_attr_not": any_attr_not,
            "all_attr_equals": all_attr_equals,
        }

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from ansible_collections.aursu.general.plugins.plugin_utils.packages import PackageNames, PackagePins

DOCUMENTATION = r"""
name: packages
short_description: Validate package specifications - names, and name to exact version pins
version_added: 1.9.0
author:
  - Alexander Ursu (@aursu)
description:
  - C(validate_package_names) accepts a package name or a list of names, every one a non-empty
    string. An empty list is valid.
  - C(validate_package_pins) accepts a non-empty map of package name to exact version, every
    version a non-empty string. An unquoted YAML version (C(0.39) a float, C(1.10) read as
    C(1.1)) or an empty value is refused, and the error names the package.
  - Both return C(true) or fail the task with a message; use them in M(ansible.builtin.assert).
  - The optional argument is the variable name used in the message.
options:
  _input:
    description: The package name(s), or the map of package to version.
    type: raw
    required: true
  name:
    description: Name of the variable being checked, for the error message.
    type: str
    default: packages
"""

EXAMPLES = r"""
- name: Refuse unpinned packages
  ansible.builtin.assert:
    that: docker_packages | aursu.general.validate_package_pins('docker_packages')
    quiet: true
# docker_packages: {docker-buildx-plugin: 0.39} fails with
#   'docker_packages['docker-buildx-plugin']' must be an exact version string, got 0.39. Quote it in YAML.

- name: Refuse a malformed package list
  ansible.builtin.assert:
    that: process_disks_packages | aursu.general.validate_package_names('process_disks_packages')
"""

RETURN = r"""
_value:
  description: C(true) when the specification is valid; otherwise the filter fails.
  type: bool
"""


def validate_package_names(value, name='packages'):
    PackageNames(value, name)
    return True


def validate_package_pins(pins, name='packages'):
    PackagePins(pins, name)
    return True


class FilterModule(object):
    def filters(self):
        return {
            'validate_package_names': validate_package_names,
            'validate_package_pins': validate_package_pins,
        }

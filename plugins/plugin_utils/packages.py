# -*- coding: utf-8 -*-
# Copyright (c) 2026, Alexander Ursu <alexander.ursu@gmail.com>
# SPDX-License-Identifier: MIT
"""
Validation of package specifications: package names, and name -> exact version pins.

Shared by the filters in this collection and by other collections' controller-side
plugins (aursu.lvm_setup, aursu.dockerinstall), so that one rule decides what a
valid package specification is.
"""

from ansible.errors import AnsibleFilterError


class PackageNames:
    """A package name or a list of them, every one a non-empty string.

    An empty list is valid: it means nothing needs installing.
    """

    def __init__(self, value, name='packages'):
        names = [value] if isinstance(value, str) else value
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            raise AnsibleFilterError(
                f"'{name}' must be a package name or a list of package names, got {value!r}."
            )
        self.names = tuple(names)


class PackagePins:
    """A non-empty map of package name to the exact version to install.

    Every version must be a non-empty string. YAML turns an unquoted version
    into a number - 0.39 stays a float, 1.10 becomes 1.1 - and an empty value
    into null; both are refused, naming the package, rather than installed.
    """

    def __init__(self, pins, name='packages'):
        if not isinstance(pins, dict) or not pins:
            raise AnsibleFilterError(
                f"'{name}' must be a non-empty map of package names to exact versions, got {pins!r}."
            )
        for package, version in pins.items():
            if not isinstance(package, str) or not package.strip():
                raise AnsibleFilterError(f"'{name}' has an empty or non-string package name: {package!r}.")
            if not isinstance(version, str) or not version.strip():
                hint = ' Quote it in YAML.' if isinstance(version, (int, float)) else ''
                raise AnsibleFilterError(
                    f"'{name}[{package!r}]' must be an exact version string, got {version!r}.{hint}"
                )
        self.pins = dict(pins)

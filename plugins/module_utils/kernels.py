# -*- coding: utf-8 -*-
# Copyright (c) 2026, Alexander Ursu <alexander.ursu@gmail.com>
# SPDX-License-Identifier: MIT
"""
Inventory of the kernels installed on a host.

Shared by the read-only M(aursu.general.kernel_info) and by modules elsewhere
that remove kernels: a module that changes state reads the current state itself,
through this code, at the moment it acts (docs/design/collection-boundaries.md).
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import re

DOCUMENTATION = r'''
---
module_utils: kernels
author: Alexander Ursu
short_description: Inventory of installed kernels and the packages that make them up
version_added: "1.8.0"
description:
  - Groups installed packages into kernels by the ABI version their names carry
    (C(linux-image-6.17.0-35-generic), C(linux-hwe-6.17-tools-6.17.0-35),
    C(linux-main-modules-zfs-7.0.0-43-generic)) rather than by a list of known
    prefixes, because the set of per-kernel packages changes between kernel series.
  - Marks the running kernel and the newest one, and measures each kernel's files
    in C(/boot).
  - Debian and Ubuntu (dpkg). RPM-based systems are not covered yet.
'''

EXAMPLES = r'''
from ansible_collections.aursu.general.plugins.module_utils.kernels import DebianKernelInventory

inventory = DebianKernelInventory(module)
kernels = inventory.collect()
# [{'version': '6.17.0-35', 'releases': ['6.17.0-35-generic'], 'packages': [...],
#   'running': False, 'latest': False, 'boot_bytes': 109134925}, ...]
'''

RETURN = r'''
Kernel:
  description: One installed kernel - its ABI version and every package carrying it.
  type: class
DebianKernelInventory:
  description: Reads the dpkg database and C(/boot) and returns the kernels, oldest first.
  type: class
'''

# A per-kernel package ends in the kernel's ABI version, optionally followed by
# the flavour: linux-modules-6.17.0-35-generic, linux-hwe-6.17-headers-6.17.0-35.
# Meta packages (linux-generic-hwe-24.04, linux-headers-3.0) do not match: their
# trailing number is not of the x.y.z-n form.
DEBIAN_KERNEL_PACKAGE = re.compile(
    r'^(?P<prefix>linux-.+?)-(?P<version>\d+\.\d+\.\d+-\d+)(?:-(?P<flavour>[a-z][a-z0-9]*))?$'
)

# Packages whose presence makes a version a bootable kernel; the release string
# they carry (version-flavour) is what `uname -r` reports.
DEBIAN_IMAGE_PREFIXES = ('linux-image', 'linux-image-unsigned')

# Files a kernel release places in /boot.
BOOT_FILES = ('vmlinuz-%s', 'initrd.img-%s', 'System.map-%s', 'config-%s')


class Kernel:
    """One installed kernel: its ABI version and every package carrying it."""

    def __init__(self, version):
        self.version = version
        self.packages = []
        self.releases = []

    @property
    def sort_key(self):
        # Numeric, so 6.17.0-9 sorts before 6.17.0-14.
        return tuple(int(part) for part in re.split(r'[.-]', self.version))

    @property
    def has_image(self):
        return bool(self.releases)

    def boot_bytes(self, boot_dir):
        total = 0
        for release in self.releases:
            for pattern in BOOT_FILES:
                path = os.path.join(boot_dir, pattern % release)
                if os.path.isfile(path):
                    total += os.path.getsize(path)
        return total


class DebianKernelInventory:
    """Kernels installed through dpkg, oldest first."""

    QUERY_FORMAT = '${Package}\t${db:Status-Abbrev}\n'

    def __init__(self, module, boot_dir='/boot'):
        self.module = module
        self.boot_dir = boot_dir

    @staticmethod
    def parse(text):
        """Group dpkg-query output into Kernel objects, oldest first.

        Only packages with files on disk count. The second letter of the status
        abbreviation is the current state: `n` (not installed) and `c` (only
        configuration files left) are skipped; a half-configured `iF` package
        still occupies /boot and is kept.
        """
        kernels = {}
        for line in text.splitlines():
            fields = line.split('\t')
            if len(fields) < 2 or len(fields[1]) < 2 or fields[1][1] in ('n', 'c'):
                continue
            match = DEBIAN_KERNEL_PACKAGE.match(fields[0])
            if not match:
                continue
            kernel = kernels.setdefault(match.group('version'), Kernel(match.group('version')))
            kernel.packages.append(fields[0])
            if match.group('prefix') in DEBIAN_IMAGE_PREFIXES and match.group('flavour'):
                release = '%s-%s' % (match.group('version'), match.group('flavour'))
                if release not in kernel.releases:
                    kernel.releases.append(release)
        return sorted(kernels.values(), key=lambda kernel: kernel.sort_key)

    def query(self):
        command = [self.module.get_bin_path('dpkg-query', required=True),
                   '-W', '-f', self.QUERY_FORMAT, 'linux-*']
        # Measured on Ubuntu 24.04: exit 0 when the pattern matches, exit 1 with
        # empty output when no package matches it at all (a container, say) -
        # an empty inventory, not a failure.
        rc, out, err = self.module.run_command(command)
        if rc == 1 and not out.strip():
            return ''
        if rc != 0:
            self.module.fail_json(msg='dpkg-query failed', rc=rc, stdout=out, stderr=err)
        return out

    def collect(self, running_release=None):
        running_release = running_release or os.uname()[2]
        kernels = self.parse(self.query())
        bootable = [kernel for kernel in kernels if kernel.has_image]
        latest = bootable[-1].version if bootable else None
        return [{
            'version': kernel.version,
            'releases': kernel.releases,
            'packages': sorted(kernel.packages),
            'running': running_release in kernel.releases,
            'latest': kernel.version == latest,
            'boot_bytes': kernel.boot_bytes(self.boot_dir),
        } for kernel in kernels]

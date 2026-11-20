#!/usr/bin/python
# -*- coding: utf-8 -*-

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r"""
module: kernel_info

short_description: List the installed kernels, their packages and their /boot footprint

version_added: "1.8.0"

description:
  - Returns every installed kernel with all the packages that carry its ABI version, whether it
    is running, whether it is the newest, and how many bytes its files take in C(/boot).
  - Packages are grouped by the ABI version in their names, not by a list of known prefixes, so a
    package a new kernel series introduces (C(linux-main-modules-zfs-7.0.0-43-generic)) is found
    without a code change.
  - Read-only. Modules that remove kernels read the same inventory themselves through
    C(aursu.general.plugins.module_utils.kernels) rather than taking this module's output.
  - Debian and Ubuntu only for now; the module fails on a host without C(dpkg-query).

options:
  boot_dir:
    description:
      - Directory holding the kernel images and initramfs files.
    type: path
    default: /boot

author:
  - Alexander Ursu (@aursu)
"""

EXAMPLES = r"""
- name: Read the installed kernels
  aursu.general.kernel_info:
  register: kernels

- name: Show the kernels that are neither running nor the newest
  ansible.builtin.debug:
    msg: "{{ kernels.installed_kernels | rejectattr('running') | rejectattr('latest') | map(attribute='version') }}"
"""

RETURN = r"""
installed_kernels:
  description: Installed kernels, oldest first.
  returned: always
  type: list
  elements: dict
  contains:
    version:
      description: ABI version, as it appears in package names.
      type: str
      sample: 6.17.0-35
    releases:
      description: Bootable releases of this version, as C(uname -r) reports them. Empty when only
        leftover packages (headers, tools) remain without an image.
      type: list
      elements: str
      sample: [6.17.0-35-generic]
    packages:
      description: Every installed package carrying this version.
      type: list
      elements: str
    running:
      description: Whether the running kernel is one of this version's releases.
      type: bool
    latest:
      description: Whether this is the newest version that has an image.
      type: bool
    boot_bytes:
      description: Total size of this version's files in C(boot_dir).
      type: int
running_release:
  description: The running kernel, as C(uname -r) reports it.
  returned: always
  type: str
  sample: 7.0.0-43-generic
"""

import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aursu.general.plugins.module_utils.kernels import DebianKernelInventory


def main():
    module = AnsibleModule(
        argument_spec=dict(
            boot_dir=dict(type='path', default='/boot'),
        ),
        supports_check_mode=True,
    )
    module.run_command_environ_update = {
        'LANG': 'C', 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LC_CTYPE': 'C',
    }

    running_release = os.uname()[2]
    inventory = DebianKernelInventory(module, boot_dir=module.params['boot_dir'])

    module.exit_json(
        changed=False,
        installed_kernels=inventory.collect(running_release=running_release),
        running_release=running_release,
    )


if __name__ == '__main__':
    main()

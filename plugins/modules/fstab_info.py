#!/usr/bin/python
# -*- coding: utf-8 -*-

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r"""
module: fstab_info

short_description: Gather the static mount table from /etc/fstab

version_added: "1.5.0"

description:
  - Reads the static mount table with C(findmnt --fstab) and returns it as structured data.
  - This is deliberately distinct from M(aursu.general.dev_info), which reports the B(live)
    mount table. The two can disagree, and the disagreement is what matters. The live table
    shows the kernel's effective options and the device as actually mounted, while fstab shows
    what will be used at the B(next boot).
  - Only fstab carries the boot-behaviour directives C(nofail) and C(_netdev). They never appear
    in the live table, so a check for them against live options can never succeed.
  - Lookup is by mount point (C(path)) rather than by device on purpose. A stale fstab source
    cannot be resolved back to a device, so a device-keyed lookup silently returns nothing for
    exactly the entries that are broken.

options:
  path:
    description:
      - Restrict the result to the entry with this mount point.
      - When omitted the whole table is returned.
    type: path
    required: false
    aliases: [mountpoint, target]

author:
  - Alexander Ursu (@aursu)
"""

EXAMPLES = r"""
- name: Read the whole static mount table
  aursu.general.fstab_info:
  register: fstab

- name: Read the fstab entry for one mount point
  aursu.general.fstab_info:
    path: /mnt/disks/data1
  register: fstab

- name: Fail when a non-root mount would block boot
  ansible.builtin.assert:
    that:
      - fstab.entry is not none
      - "'nofail' in fstab.entry.options"
"""

RETURN = r"""
fstab:
  description:
    - Every entry in the static mount table, in file order.
    - When O(path) is set this is filtered to the matching entry.
  returned: always
  type: list
  elements: dict
  contains:
    target:
      description: Mount point.
      type: str
    source:
      description: Device, UUID= or LABEL= spec as written in the file.
      type: str
    fstype:
      description: Filesystem type.
      type: str
    options:
      description: Mount options exactly as written in the file.
      type: str
  sample:
    - target: /mnt/disks/data1
      source: /dev/data/data1
      fstype: xfs
      options: defaults,nofail

entry:
  description:
    - The single matching entry when O(path) is given, otherwise null.
    - Null also when O(path) is given but no such mount point is declared.
  returned: when path is specified
  type: dict

is_exists:
  description: Whether /etc/fstab could be read at all.
  returned: always
  type: bool
"""

import json
import os

from ansible.module_utils.basic import AnsibleModule

FSTAB_PATH = '/etc/fstab'

# findmnt is asked for an explicit column set so the output shape does not drift
# with the util-linux default, which differs between releases.
FSTAB_COLUMNS = 'TARGET,SOURCE,FSTYPE,OPTIONS,FREQ,PASSNO'


def run_findmnt_fstab(module, path=None):
    """Return the static mount table as a list of dicts.

    An empty list means "nothing matched", which is not an error: a mount point
    that is absent from fstab is a legitimate and interesting state.
    """
    command = ['findmnt', '--fstab', '-J', '-o', FSTAB_COLUMNS]

    if path is not None:
        # --mountpoint matches the target column exactly, so a stale or
        # unresolvable source cannot hide the entry.
        command += ['--mountpoint', path]

    rc, out, _err = module.run_command(command)

    # findmnt exits 1 when nothing matched; that is not a failure here.
    if rc != 0 or not out.strip():
        return []

    try:
        data = json.loads(out)
    except ValueError:
        return []

    return data.get('filesystems', [])


def main():
    module = AnsibleModule(
        argument_spec=dict(
            path=dict(type='path', required=False, aliases=['mountpoint', 'target']),
        ),
        supports_check_mode=True,
    )
    module.run_command_environ_update = {
        'LANG': 'C', 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LC_CTYPE': 'C',
    }

    path = module.params['path']

    result = {
        'is_exists': os.path.exists(FSTAB_PATH),
        'fstab': [],
        'entry': None,
    }

    if not result['is_exists']:
        module.exit_json(changed=False, **result)

    entries = run_findmnt_fstab(module, path)
    result['fstab'] = entries

    if path is not None:
        result['entry'] = entries[0] if entries else None

    module.exit_json(changed=False, **result)


if __name__ == '__main__':
    main()

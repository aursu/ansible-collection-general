#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from ansible.errors import AnsibleFilterError
from ansible_collections.aursu.general.plugins.plugin_utils.mounts import MountTable

DOCUMENTATION = r"""
name: mounts
short_description: Require a directory to be a mount point of its own
version_added: 1.10.0
author:
  - Alexander Ursu (@aursu)
description:
  - C(validate_mount_point) takes C(ansible_facts.mounts) and a path, and returns C(true) when the
    path is a mount point of its own. Otherwise the task fails, and the message names the mount
    that actually holds the path and its device - for example that C(/var/lib/docker) is still on
    C(/) from C(/dev/nvme0n1p3).
  - Prefixes are compared by path component (C(/var/lib/docker2) is not under C(/var/lib/docker)).
options:
  _input:
    description: The mount table, C(ansible_facts.mounts).
    type: list
    elements: dict
    required: true
  path:
    description: Absolute path that must be a mount point.
    type: str
    required: true
"""

EXAMPLES = r"""
- name: Refuse unless /var/lib/docker is its own volume
  ansible.builtin.assert:
    that: ansible_facts.mounts | aursu.general.validate_mount_point('/var/lib/docker')
    quiet: true
# Fails with: /var/lib/docker is not a mount point: it is on / (/dev/nvme0n1p3).
"""

RETURN = r"""
_value:
  description: C(true) when the path is a mount point; otherwise the filter fails.
  type: bool
"""


def validate_mount_point(mounts, path):
    table = MountTable(mounts)
    if table.is_mount_point(path):
        return True
    entry = table.holding(path)
    if entry is None:
        raise AnsibleFilterError(f"{path} is not a mount point, and no mount in the table holds it.")
    raise AnsibleFilterError(
        f"{path} is not a mount point: it is on {entry['mount']} ({entry.get('device', 'unknown device')})."
    )


class FilterModule(object):
    def filters(self):
        return {
            'validate_mount_point': validate_mount_point,
        }

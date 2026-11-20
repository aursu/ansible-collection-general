# -*- coding: utf-8 -*-
# Copyright (c) 2026, Alexander Ursu <alexander.ursu@gmail.com>
# SPDX-License-Identifier: MIT
"""
Which mount holds a path, read from ``ansible_facts.mounts``.

A play that must not write to the root filesystem by accident (Docker's data
directory on its own volume, say) needs to know that a directory is a mount
point of its own - not merely that it exists.
"""

import posixpath

from ansible.errors import AnsibleFilterError


class MountTable:
    """The mount entries of ``ansible_facts.mounts`` that carry a mount point."""

    def __init__(self, mounts):
        if not isinstance(mounts, list):
            raise AnsibleFilterError(
                f"Expected the mount table (ansible_facts.mounts) to be a list, got {type(mounts).__name__}."
            )
        self.entries = [m for m in mounts if isinstance(m, dict) and isinstance(m.get('mount'), str)]

    def holding(self, path):
        """The entry whose mount point is the longest prefix of ``path``, or None.

        Prefixes are compared by path component, so /var/lib/docker2 is not under
        /var/lib/docker. When one mount point appears twice (a mount over a
        mount), the later entry wins, as the kernel's later mount shadows the
        earlier one.
        """
        if not isinstance(path, str) or not posixpath.isabs(path):
            raise AnsibleFilterError(f"Expected an absolute path, got {path!r}.")
        path = posixpath.normpath(path)
        best, best_len = None, -1
        for entry in self.entries:
            point = posixpath.normpath(entry['mount'])
            if path == point or point == '/' or path.startswith(point + '/'):
                if len(point) >= best_len:
                    best, best_len = entry, len(point)
        return best

    def is_mount_point(self, path):
        entry = self.holding(path)
        return entry is not None and posixpath.normpath(entry['mount']) == posixpath.normpath(path)

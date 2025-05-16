#!/usr/bin/python
# -*- coding: utf-8 -*-

#  Copyright (c) 2025 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r"""
module: dev_info

short_description: Gather information about a file system object

version_added: "1.3.0"

description:
  - This module retrieves information about a file system object such as a block device, regular file, socket, FIFO, etc.
  - It uses Python's os.stat to collect metadata and conditionally gathers additional details for block devices using blkid and findmnt.

options:
  dev:
    description:
      - Target path to file system object.
    type: path
    required: true
    aliases: [device]

author:
  - Alexander Ursu (@aursu)
"""

EXAMPLES = r"""
- name: Gather information about /dev/sdb1
  aursu.general.dev_info:
    dev: /dev/sdb1
  register: dev_info
"""

RETURN = r"""
is_exists:
  description: Whether the specified path exists on the system.
  returned: always
  type: bool
  sample: true

stat:
  description: File status information as defined by POSIX stat(2).
  returned: when is_exists is true
  type: dict
  contains:
    dev:
      description: Device ID of device containing file.
      type: int
    ino:
      description: File serial number (inode).
      type: int
    mode:
      description: Mode of file (permissions and file type).
      type: int
    nlink:
      description: Number of hard links to the file.
      type: int
    uid:
      description: User ID of the file owner.
      type: int
    gid:
      description: Group ID of the file owner.
      type: int
    rdev:
      description: Device ID (if special file).
      type: int
    size:
      description: File size in bytes.
      type: int
    atime:
      description: Time of last access (Unix timestamp).
      type: float
    mtime:
      description: Time of last data modification (Unix timestamp).
      type: float
    ctime:
      description: Time of last status change (e.g. chmod, chown). Not creation time.
      type: float
    error:
      description: Error message if stat failed (only present on failure).
      type: str
      returned: when stat() fails

filetype:
  description: >
    File type indicator in the same format as the first character in `ls -l` output:
    - b = block special device  
    - c = character special device  
    - d = directory  
    - - = regular file  
    - l = symbolic link  
    - p = FIFO (named pipe)  
    - s = socket  
  returned: when is_exists is true
  type: str
  sample: 'b'

blkid:
  description: Key-value pairs from 'blkid --output export' if applicable.
  returned: when filetype is 'b'
  type: dict

mount:
  description: Matching mount point entry from 'findmnt -J' if available.
  returned: when filetype is 'b' and device is mounted
  type: dict
"""

import os
import json
import stat
from ansible.module_utils.basic import AnsibleModule

def run_findmnt(module, dev=None):
    rc, out, _ = module.run_command(['findmnt', '-J'])

    result = []
    if rc != 0:
        return [{"rc": rc, "out": out}]

    try:
        data = json.loads(out)
    except Exception:
        return [{"rc": rc, "out": out, "json": False}]

    if dev is None:
        return data

    for entry in data.get('filesystems', []):
        if entry.get('source') == dev:
            result.append(entry)

    return result

def run_blkid(module, dev):
    rc, out, _ = module.run_command(['blkid', '--output', 'export', dev])
    if rc != 0:
        return None

    renames = {
        'devname': 'dev_name',
        'partlabel': 'part_label',
        'partuuid': 'part_uuid',
    }

    data = {}
    for line in out.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            key = renames.get(k.lower(), k.lower())
            data[key] = v
    return data


def classify_file_type(mode):
    # ls comman notation
    if stat.S_ISBLK(mode):
        return 'b' # block special
    if stat.S_ISCHR(mode):
        return 'c' # character special
    if stat.S_ISREG(mode):
        return '-' # regular
    if stat.S_ISDIR(mode):
        return 'd' # directory
    if stat.S_ISFIFO(mode):
        return 'p' # FIFO special
    if stat.S_ISSOCK(mode):
        return 's' # socket
    if stat.S_ISLNK(mode):
        return 'l' # symbolic link
    return None

def main():
    module = AnsibleModule(
        argument_spec=dict(
            dev=dict(type='path', required=True, aliases=['device']),
        ),
        supports_check_mode=True
    )
    module.run_command_environ_update = {'LANG': 'C', 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LC_CTYPE': 'C'}

    dev = module.params['dev']

    result = {'is_exists': False}

    if not os.path.exists(dev):
        module.exit_json(changed=False, **result)

    result['is_exists'] = True

    try:
      stat_info = os.stat(dev)
      result['stat'] = dict(
          mode=stat_info.st_mode,
          ino=stat_info.st_ino,
          dev=stat_info.st_dev,
          nlink=stat_info.st_nlink,
          uid=stat_info.st_uid,
          gid=stat_info.st_gid,
          rdev=stat_info.st_rdev,
          size=stat_info.st_size,
          atime=stat_info.st_atime,
          mtime=stat_info.st_mtime,
          ctime=stat_info.st_ctime,
      )
    except Exception as e:
      result['stat'] = {'error': str(e)}

    filetype = classify_file_type(stat_info.st_mode)
    result['filetype'] = filetype

    if filetype == 'b':
        blkid_info = run_blkid(module, dev)
        if blkid_info:
            result['blkid'] = blkid_info

        mount_info = run_findmnt(module, dev)
        if mount_info:
            result['mount'] = mount_info

    module.exit_json(changed=False, **result)

if __name__ == '__main__':
    main()

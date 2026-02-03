#!/usr/bin/python
# -*- coding: utf-8 -*-

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r"""
module: sshd_info

short_description: Gather configuration details from sshd_config and included files

version_added: "1.0.0"

description:
  - Parses OpenSSH server configuration recursively.
  - Implements 'First Match Wins' strategy typical for SSHD global options.
  - Returns the effective value and a list of all files defining the option.

options:
  config_path:
    description: Path to the main sshd configuration file.
    type: path
    default: "/etc/ssh/sshd_config"

author:
  - Alexander Ursu (@aursu)
"""

EXAMPLES = r"""
- name: Gather information about SSHd configuration
  aursu.general.sshd_info:
  register: sshd_info
"""

RETURN = r"""
sshd_config:
  description: Parsed SSHD configuration.
  returned: always
  type: dict
  sample:
    PasswordAuthentication:
      value: "yes"
      location: "/etc/ssh/sshd_config.d/50-cloud-init.conf"
      appearance:
        - "/etc/ssh/sshd_config.d/50-cloud-init.conf"
        - "/etc/ssh/sshd_config"
"""

import os
import glob
import shlex
from ansible.module_utils.basic import AnsibleModule

class SshOptionRegistry:
    """
    Responsibility: Store configuration options and implement 'First Match Wins' logic.
    Acts as a repository for parsed settings.
    """
    def __init__(self, scope="global"):
        self.scope = scope
        # Internal storage: { 'lowercase_key': { 'name': Str, 'value': Str, ... } }
        self._storage = {}

    def register(self, key, value, filepath):
        """
        Registers an option found in a config file.
        If the option is new, it's the effective value.
        If it exists, we just append the filepath to appearance list.
        """
        normalized_key = key.lower()

        if normalized_key not in self._storage:
            # First time seeing this option -> It is the EFFECTIVE value
            self._storage[normalized_key] = {
                'name': key,
                'value': value,
                'location': filepath,
                'appearance': [filepath]
            }
        else:
            # Option already defined previously -> Just log the occurrence
            entry = self._storage[normalized_key]
            if filepath not in entry['appearance']:
                entry['appearance'].append(filepath)

    def to_dict(self):
        """
        Converts internal storage to the final output format.
        Removes normalization keys.
        """
        result = {}
        for data in self._storage.values():
            # Create a copy to avoid mutating internal state if called multiple times
            item = data.copy()
            key_name = item.pop('name')
            result[key_name] = item
        return result


class SshConfigParser:
    """
    Responsibility: Read files, handle 'Include' recursion, parse lines.
    """
    def __init__(self, base_dir="/etc/ssh"):
        self.current_scope = "global"
        self.registry = {"global": SshOptionRegistry(scope=self.current_scope)}
        self.base_dir = base_dir
        self.processed_files = set()
        self.parent_scope = None
        self.current_file = None # e.g. default
        self.max_depth = 20

    def parse(self, filepath, depth=0):
        if depth > self.max_depth:
            return # Circuit breaker for infinite recursion

        # Resolve symlinks and absolute paths
        abs_path = os.path.abspath(filepath)

        # Avoid processing the exact same file object twice in one stack (loops)
        # However, SSHD technically allows including the same file, but for static analysis
        # usually we want to process it to find the definitions.
        # But to be safe against loops like A includes B includes A:
        if abs_path in self.processed_files:
            return

        self.processed_files.add(abs_path)

        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            return

        self.current_file = abs_path

        try:
            with open(abs_path, 'r') as f:
                lines = f.readlines()
        except (IOError, OSError):
            return # Skip unreadable files

        for line in lines:
            self._process_line(line, depth)

        # After finishing this file, restore previous scope
        self.current_scope = self.parent_scope if self.parent_scope else "global"

    def _process_line(self, line, depth):
        line = line.strip()
        if not line or line.startswith('#'):
            return

        try:
            parts = shlex.split(line)
        except ValueError:
            return # Syntax error in config file, skip

        if not parts:
            return

        key = parts[0]
        # Reconstruct value (everything after key)
        value = " ".join(parts[1:]) if len(parts) > 1 else ""

        if key.lower() == 'include':
            self._handle_include(value, depth)
        elif key.lower() == 'match':
            self.parent_scope = self.current_scope
            self.current_scope = value
            if self.current_scope not in self.registry:
                self.registry[self.current_scope] = SshOptionRegistry(scope=self.current_scope)
        else:
            self.registry[self.current_scope].register(key, value, self.current_file)

    def _handle_include(self, pattern, depth):
        """
        Handles the Include directive logic.
        """
        # If path is relative, it is relative to /etc/ssh (usually),
        # NOT the current file's directory.
        if not os.path.isabs(pattern):
            pattern = os.path.join(self.base_dir, pattern)

        # Sort is crucial because SSHD loads includes in lexical order
        matched_files = sorted(glob.glob(pattern))

        # save current file context
        current_file = self.current_file

        for file_path in matched_files:
            # Recursively parse
            # We must create a new recursion branch
            # We intentionally do not remove from processed_files after return
            # to prevent loops.
            self.parse(file_path, depth + 1)

            # restore current file context
            self.current_file = current_file

def main():
    module = AnsibleModule(
        argument_spec=dict(
            config_path=dict(type='path', default='/etc/ssh/sshd_config'),
        ),
        supports_check_mode=True
    )

    config_path = module.params['config_path']
    base_ssh_dir = os.path.dirname(config_path)


    # 2. Initialize Parser with Registry (The Worker)
    parser = SshConfigParser(base_dir=base_ssh_dir)

    # 3. Execute
    if os.path.exists(config_path):
        parser.parse(config_path)
    else:
        module.fail_json(msg=f"Main config file not found: {config_path}")

    registry = parser.registry

    config_data = registry.get("global").to_dict()
    for scope, reg in registry.items():
        if scope == "global":
            continue
        if "Match" in config_data:
            config_data["Match"] += [{"title": scope, **reg.to_dict()}]
        else:
            config_data["Match"] = [{"title": scope, **reg.to_dict()}]

    # 4. Return Data
    module.exit_json(changed=False, sshd_config=config_data)

if __name__ == '__main__':
    main()
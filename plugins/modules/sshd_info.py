#!/usr/bin/python
# -*- coding: utf-8 -*-

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import io
import glob
import os
import shlex
from ansible.module_utils.basic import AnsibleModule

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

class OptionStore:
    """
    Stores options for a specific scope (Global or a particular Match condition).
    Implements 'First Match Wins' logic.
    """
    def __init__(self, scope_name):
        self.scope_name = scope_name
        self.location = None
        self.appearance = []
        # Data structure: { "lower_key": { "name": "RealKey", "value": "...", ... } }
        self._options = {}

    def update_appearance(self, filepath):
        """
        Called each time the parser encounters a "Match ..." line
        """
        if self.location is None:
            self.location = filepath

        if filepath not in self.appearance:
            self.appearance.append(filepath)

    def add(self, key, value, filepath):
        k_lower = key.lower()
        if k_lower not in self._options:
            # First occurrence of the option becomes the effective value
            self._options[k_lower] = {
                "name": key,
                "value": value,
                "location": filepath,
                "appearance": [filepath]
            }
        else:
            # Option already exists (shadowed) — append file to appearance list
            if filepath not in self._options[k_lower]["appearance"]:
                self._options[k_lower]["appearance"].append(filepath)

    def to_dict(self):
        # Convert to external format: Key -> { value, location, appearance }
        # Remove internal "name" key from the result
        options_export = {
            v["name"]: {k: val for k, val in v.items() if k != "name"}
            for v in self._options.values()
        }

        if self.scope_name == "global":
            return options_export

        return {
            "condition": self.scope_name,
            "location": self.location,
            "appearance": self.appearance,
            "options": options_export
        }

class SshConfigParser:
    def __init__(self, base_dir="/etc/ssh"):
        self.base_dir = base_dir

        # Registry: key = scope identifier string, value = OptionStore instance
        self.registry = {
            "global": OptionStore("global")
        }

    def _get_store(self, scope):
        if scope not in self.registry:
            self.registry[scope] = OptionStore(scope)
        return self.registry[scope]

    def parse(self, filepath, current_scope="global", depth=0, call_stack=None):
        """
        Recursive configuration parser.
        current_scope: context inherited from parent file (for Include directives).
        call_stack: list of files currently being parsed (to prevent loops A->B->A).
        """
        if depth > 20:
            return

        if call_stack is None:
            call_stack = set()

        abs_path = os.path.abspath(filepath)

        if abs_path in call_stack:
            return

        if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
            return

        new_stack = call_stack.copy()
        new_stack.add(abs_path)

        try:
            # io.open is safer for mixed Python 2/3 environments
            with io.open(abs_path, 'r', encoding="utf-8", errors='ignore') as f:
                lines = f.readlines()
        except (IOError, OSError):
            return

        # Local scope variable for the CURRENT file.
        # Initially set to the value passed by parent (for Include within Match blocks).
        local_scope = current_scope

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                parts = shlex.split(line)
            except ValueError:
                continue

            if not parts:
                continue

            key = parts[0]
            value = " ".join(parts[1:]) if len(parts) > 1 else ""

            if key.lower() == "include":
                # Recursively process included files with CURRENT local_scope
                self._handle_include(value, local_scope, depth, new_stack)

            elif key.lower() == "match":
                # Switch context within the current file
                # Special handling for 'Match All' -> resets to global
                if value.lower() == "all":
                    local_scope = "global"
                else:
                    local_scope = value
                    store = self._get_store(local_scope)
                    store.update_appearance(abs_path)
            else:
                # Regular option — write to current scope store
                store = self._get_store(local_scope)
                store.add(key, value, abs_path)

        # Upon function exit (EOF), local_scope is destroyed.
        # Control returns to the caller with its own local_scope version.
        # This emulates Match block closure at end of file.

    def _handle_include(self, pattern, active_scope, depth, call_stack):
        if not os.path.isabs(pattern):
            pattern = os.path.join(self.base_dir, pattern)

        # Sorting is essential for deterministic processing order
        for file_path in sorted(glob.glob(pattern)):
            self.parse(file_path, active_scope, depth + 1, call_stack)

    def get_structured_data(self):
        """
        Constructs the output data structure:
        Root -> Global Options
        Root["Match"] -> List of Dicts
        """
        # 1. Use global options as the base structure
        result = self.registry["global"].to_dict()

        # 2. Build list of Match blocks
        match_list = []
        for scope, store in self.registry.items():
            if scope == "global":
                continue

            # Convert store to dictionary format
            match_list.append(store.to_dict())

        # 3. Include Match blocks in result if any exist
        if match_list:
            result["Match"] = match_list

        return result

def main():
    module = AnsibleModule(
        argument_spec=dict(
            config_path=dict(type="path", default="/etc/ssh/sshd_config"),
        ),
        supports_check_mode=True
    )

    config_path = module.params["config_path"]
    base_dir = os.path.dirname(config_path)

    parser = SshConfigParser(base_dir=base_dir)

    if os.path.exists(config_path):
        parser.parse(config_path, "global")
    else:
        module.fail_json(msg=f"Config file not found: {config_path}")

    # Retrieve data in the required format
    final_structure = parser.get_structured_data()

    module.exit_json(changed=False, sshd_config=final_structure)

if __name__ == "__main__":
    main()
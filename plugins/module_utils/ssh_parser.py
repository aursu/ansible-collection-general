# -*- coding: utf-8 -*-
# Copyright (c) 2026, Alexander Ursu <alexander.ursu@gmail.com>
# SPDX-License-Identifier: MIT

"""
OpenSSH Configuration Parser Utilities.

Provides `SshConfigParser` and `OptionStore` classes to recursively parse
sshd_config files, handling 'Include' directives and 'Match' blocks
with 'First Match Wins' logic.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import io
import glob
import os
import shlex

DOCUMENTATION = r'''
---
module_utils: ssh_parser
author: Alexander Ursu
short_description: Recursively parse OpenSSH server configuration
version_added: "1.0.0"
description:
  - This module_utils library provides classes to parse C(sshd_config) and its included files.
  - It resolves the effective configuration by applying OpenSSH's "First Match Wins" strategy.
  - It tracks the location (file path) and appearance (duplicates) of every option.
  - It distinguishes between Global scope and Match block scopes.
'''

EXAMPLES = r'''
from ansible_collections.aursu.general.plugins.module_utils.ssh_parser import SshConfigParser

# 1. Initialize the parser
parser = SshConfigParser(base_dir="/etc/ssh")

# 2. Parse the main configuration file (it will follow Includes recursively)
parser.parse("/etc/ssh/sshd_config")

# 3. Get the structured data
data = parser.get_structured_data()

# Example access to global option
port_info = data.get('Port')
# {'value': '22', 'location': '/etc/ssh/sshd_config', 'appearance': ['...']}

# Example access to Match blocks
match_blocks = data.get('Match', [])
for block in match_blocks:
    if block['condition'] == 'User bob':
        print(block['options']['X11Forwarding'])
'''

RETURN = r'''
SshConfigParser:
  description: Main class for parsing logic.
  type: class

OptionStore:
  description: Storage class for options within a specific scope (Global or Match).
  type: class
'''

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

        # Loop protection (stack-based)
        if abs_path in call_stack:
            return

        # FIXED: Removed 'self.processed_files' check.
        # Files MUST be re-parsed if they are included in different contexts/scopes.
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

        # Include Match blocks in result if any exist
        if match_list:
            result["Match"] = match_list

        return result

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
version_added: "1.5.0"
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
# {'value': '22', 'values': ['22', '2222'], 'cumulative': True, ...}

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

# Directives where EVERY occurrence takes effect, rather than the first one
# winning and the rest being discarded.
#
# This list is measured, not assumed: each entry was verified against
# OpenSSH 9.9p1 by writing a config with two occurrences and reading back
# `sshd -T`. Several plausible candidates are deliberately absent because the
# measurement contradicted the intuition - SetEnv, PermitOpen and PermitListen
# are all first-wins.
#
# A directive missing from this list is shadowed: only its first occurrence is
# in force. Those report `value`, `location` and `appearance` and nothing more -
# the discarded values are not recorded, because `appearance` already names
# every file they would have to be removed from.
CUMULATIVE_DIRECTIVES = frozenset((
    "acceptenv",
    "allowgroups",
    "allowusers",
    "denygroups",
    "denyusers",
    "hostkey",
    "listenaddress",
    "port",
    "subsystem",
))

# sshd accepts "Key Value", "Key=Value" and "Key = Value" interchangeably.
SEPARATOR = "="

MAX_INCLUDE_DEPTH = 20


def split_directive(line):
    """Split one configuration line into (key, value).

    Handles the equals form as well as whitespace, because sshd does:
    verified against OpenSSH 9.9p1, which accepts all three spellings below.
    Returns (None, None) for a line that cannot be lexed.

    >>> split_directive("Port 22")
    ('Port', '22')
    >>> split_directive("PermitRootLogin=prohibit-password")
    ('PermitRootLogin', 'prohibit-password')
    >>> split_directive("MaxAuthTries = 5")
    ('MaxAuthTries', '5')
    >>> split_directive("AllowUsers alice bob")
    ('AllowUsers', 'alice bob')
    >>> split_directive("Subsystem sftp /usr/libexec/openssh/sftp-server")
    ('Subsystem', 'sftp /usr/libexec/openssh/sftp-server')
    >>> split_directive("Banner none")
    ('Banner', 'none')
    """
    try:
        parts = shlex.split(line)
    except ValueError:
        return None, None

    if not parts:
        return None, None

    # "Key = Value" lexes to three tokens; drop the bare separator.
    # Only drop the bare separator if the first token doesn't already contain it
    if len(parts) > 1 and parts[1] == SEPARATOR and SEPARATOR not in parts[0]:
        parts = [parts[0]] + parts[2:]

    key = parts[0]
    rest = parts[1:]

    # "Key=Value" lexes to a single token.
    if SEPARATOR in key:
        key, _, first = key.partition(SEPARATOR)
        if first:
            rest = [first] + rest

    if not key:
        return None, None

    return key, " ".join(rest)


class OptionStore:
    """
    Stores options for a specific scope (Global or a particular Match condition).
    Implements 'First Match Wins' logic.
    """
    def __init__(self, scope_name):
        self.scope_name = scope_name
        self.location = None
        self.appearance = []
        # Data structure: { "lower_key": { "name": "RealKey", "values": [...], "appearance": [...] } }
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
        """Record one occurrence of a directive.

        Two lists are kept and they are not correlated with each other:
        `values` in encounter order, and `appearance` - the files, de-duplicated
        in the same order. Nothing pairs a value with the file it came from,
        because nothing needs to. `value` is derived from the first list and
        `location` from the head of the second, and a caller acts on files, not
        on discarded values.
        """
        k_lower = key.lower()
        entry = self._options.get(k_lower)

        if entry is None:
            entry = {"name": key, "values": [], "appearance": []}
            self._options[k_lower] = entry

        entry["values"].append(value)
        if filepath not in entry["appearance"]:
            entry["appearance"].append(filepath)

    @staticmethod
    def _export_option(entry):
        """Render one directive for output.

        The shape is deliberately minimal - `value`, `location` and
        `appearance`, where `value` is the setting in force, `location` is the
        file to edit and `appearance` is every file the directive occurs in,
        which is the list to clean up. That triple is the contract other tooling
        reads.

        No record of discarded values is emitted, and none is kept internally
        either. Knowing a directive was written three times is not actionable;
        knowing which files to remove it from is, and `appearance` already says
        so.

        `value` carries a string for a shadowed directive and a **list** for a
        cumulative one, where every occurrence is in force rather than only the
        first. There is exactly one field for the setting either way; the
        `cumulative` flag, present only on those directives, says which type to
        expect. The type follows the flag and not the count, so a cumulative
        directive written once still yields a one-item list.
        """
        values = entry["values"]
        appearance = entry["appearance"]

        exported = {
            # First occurrence, and the file it was in - which is the head of
            # `appearance`, since that list is built in the same order.
            "value": values[0],
            "location": appearance[0],
            # Copied: the internal list must not be mutable through the export.
            "appearance": list(appearance),
        }

        if entry["name"].lower() in CUMULATIVE_DIRECTIVES:
            exported["value"] = list(values)
            exported["cumulative"] = True

        return exported

    def to_dict(self):
        # Convert to external format: Key -> { value, values, ... }
        # The internal "name" key is dropped from the result.
        options_export = {
            v["name"]: self._export_option(v)
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

        # Files actually read, in the order they were read, and anything that
        # went wrong while reading them. Both matter: a config audit that
        # silently skipped an unreadable drop-in is worse than one that failed,
        # because it looks like an answer.
        self.parsed_files = []
        self.errors = []

    def _record_error(self, path, reason):
        self.errors.append({"path": path, "reason": reason})

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
        abs_path = os.path.abspath(filepath)

        if depth > MAX_INCLUDE_DEPTH:
            self._record_error(
                abs_path,
                "include depth exceeded %d; not parsed" % MAX_INCLUDE_DEPTH,
            )
            return

        if call_stack is None:
            call_stack = set()

        # Loop protection (stack-based)
        if abs_path in call_stack:
            self._record_error(abs_path, "include loop; already being parsed")
            return

        # FIXED: Removed 'self.processed_files' check.
        # Files MUST be re-parsed if they are included in different contexts/scopes.
        if not os.path.exists(abs_path):
            self._record_error(abs_path, "does not exist")
            return

        if not os.path.isfile(abs_path):
            self._record_error(abs_path, "not a regular file")
            return

        new_stack = call_stack.copy()
        new_stack.add(abs_path)

        try:
            # io.open is safer for mixed Python 2/3 environments
            with io.open(abs_path, 'r', encoding="utf-8", errors='ignore') as f:
                lines = f.readlines()
        except (IOError, OSError) as exc:
            # Drop-ins are routinely mode 0600. Reading the configuration as an
            # unprivileged user must not look like a configuration with fewer
            # options in it.
            self._record_error(abs_path, "could not be read: %s" % exc)
            return

        if abs_path not in self.parsed_files:
            self.parsed_files.append(abs_path)

        # Local scope variable for the CURRENT file.
        # Initially set to the value passed by parent (for Include within Match blocks).
        local_scope = current_scope

        for lineno, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            key, value = split_directive(line)
            if key is None:
                self._record_error(
                    abs_path, "line %d could not be parsed: %s" % (lineno, line)
                )
                continue

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

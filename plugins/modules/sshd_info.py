#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

#  Copyright (c) 2026 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)

import os
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aursu.general.plugins.module_utils.ssh_parser import SshConfigParser

__metaclass__ = type

DOCUMENTATION = r"""
module: sshd_info

short_description: Gather configuration details from sshd_config and included files

version_added: "1.5.0"

description:
  - Parses OpenSSH server configuration recursively, following C(Include) directives.
  - Implements the "first match wins" rule that sshd applies, which is the opposite of the
    intuition most people bring to a configuration directory. A drop-in read early, such as one
    in C(sshd_config.d/), silently defeats the same option set later in the main file.
  - For each option it returns the winning value, every value seen, and the file each one came
    from, so that a setting which was written but does nothing is visible rather than absent.
  - Some directives accumulate instead of being shadowed - every occurrence of C(Port),
    C(ListenAddress), C(HostKey), C(AllowUsers) and their kin takes effect. For those C(value)
    is a list of all of them and C(cumulative) is true. The list of such directives was
    measured against OpenSSH 9.9p1 rather than taken from the manual page, because the
    intuition is wrong in both directions - C(SetEnv), C(PermitOpen) and C(PermitListen) do
    B(not) accumulate.
  - This reports the configuration B(as written), not as sshd computes it. Two differences are
    worth knowing - sshd canonicalises deprecated aliases, so C(prohibit-password) is reported
    here and C(without-password) by C(sshd -T); and sshd expands C(ListenAddress) against every
    C(Port) into concrete listeners, while this returns the addresses as configured.
  - Match blocks are returned as structure rather than evaluated. The module does not decide
    what applies to a given user or address, it reports what each block contains.

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
  description:
    - Parsed SSHD configuration. Global options at the root, plus a C(Match) list when Match
      blocks are present.
    - Each option carries C(value) - the setting in force, C(location) - the file it came from
      and therefore the file to edit, and C(appearance) - every file the directive occurs in,
      which is the list to clean up.
    - C(value) is a string for a shadowed directive and a B(list) for a cumulative one, where
      every occurrence is in force rather than only the first. The C(cumulative) flag, present
      only on those directives, says which to expect. A cumulative directive written once still
      yields a one-item list, so a caller never has to handle both shapes for the same
      directive.
  returned: always
  type: dict
  sample:
    PasswordAuthentication:
      value: "no"
      location: "/etc/ssh/sshd_config.d/50-cloud-init.conf"
      appearance:
        - "/etc/ssh/sshd_config.d/50-cloud-init.conf"
        - "/etc/ssh/sshd_config"
    ListenAddress:
      value: ["10.0.0.1", "10.0.0.2"]
      cumulative: true
      location: "/etc/ssh/sshd_config"
      appearance:
        - "/etc/ssh/sshd_config"

parsed_files:
  description:
    - Every file that was read, in the order it was read.
    - Includes files reached through C(Include), so it shows the drop-ins that
      were actually consulted rather than the ones that were expected to be.
  returned: always
  type: list
  elements: str
  version_added: "1.7.0"

errors:
  description:
    - Files that could not be read, includes that resolved to nothing, loops,
      depth-limit hits and lines that could not be lexed.
    - Empty on a clean parse. A non-empty list means the returned configuration
      is incomplete, which matters most when the module runs unprivileged - a
      drop-in at mode 0600 is invisible, and a silently short answer looks
      exactly like a correct one.
  returned: always
  type: list
  elements: dict
  contains:
    path:
      description: The file concerned.
      type: str
    reason:
      description: Why it was skipped.
      type: str
  version_added: "1.7.0"
"""


def main():
    module = AnsibleModule(
        argument_spec=dict(
            config_path=dict(type="path", default="/etc/ssh/sshd_config"),
        ),
        supports_check_mode=True
    )

    config_path = module.params["config_path"]
    base_dir = os.path.dirname(config_path)

    if not os.path.exists(config_path):
        module.fail_json(msg="Config file not found: %s" % config_path)

    parser = SshConfigParser(base_dir=base_dir)
    parser.parse(config_path, "global")

    module.exit_json(
        changed=False,
        sshd_config=parser.get_structured_data(),
        parsed_files=parser.parsed_files,
        errors=parser.errors,
    )


if __name__ == "__main__":
    main()

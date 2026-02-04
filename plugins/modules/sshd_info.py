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
        print(f"Parsing SSHD config from: {config_path}")
        parser.parse(config_path, "global")
    else:
        module.fail_json(msg=f"Config file not found: {config_path}")

    # Retrieve data in the required format
    final_structure = parser.get_structured_data()

    module.exit_json(changed=False, sshd_config=final_structure)

if __name__ == "__main__":
    main()

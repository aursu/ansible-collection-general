#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

#  Copyright (c) 2025 Alexander Ursu <alexander.ursu@gmail.com>
#  MIT License (see LICENSE file or https://opensource.org/licenses/MIT)
#  SPDX-License-Identifier: MIT

from __future__ import (absolute_import, division, print_function)
import json
from ansible.module_utils.basic import AnsibleModule

__metaclass__ = type

DOCUMENTATION = r"""
module: lvm_info

short_description: Gather LVM information from the system (PVs, VGs, LVs)

version_added: "1.0.0"

description:
  - This module retrieves LVM data from the system using native commands like C(pvs), C(vgs), and C(lvs).
  - It parses the JSON output of these commands and returns structured results for automation or reporting.

options:
  filter:
    description:
      - The type(s) of LVM object to retrieve.
      - Can be a single value or a comma-separated list of values.
      - Special value C(all) is equivalent to C(pvs,vgs,lvs).
    type: raw
    default: "pvs"
    choices: ["pvs", "vgs", "lvs", "all"]
  unit:
    description:
      - Unit to use when reporting sizes, passed as C(--units) to LVM tools.
      - Acceptable values: C(r), C(R), C(h), C(H), C(b), C(B), C(s), C(S), C(k), C(K), C(m), C(M), C(g), C(G), C(t), C(T), C(p), C(P), C(e), C(E)
      - Lowercase = base-2 (binary), uppercase = base-10 (decimal).
      - Default is C(m) (mebibytes).
      - For example, C(unit: G) will return sizes in gigabytes using base-10.
    type: str
    default: "m"
    choices: ["r", "R", "h", "H", "b", "B", "s", "S", "k", "K", "m", "M", "g", "G", "t", "T", "p", "P", "e", "E"]

author:
  - Alexander Ursu (@aursu)
"""

EXAMPLES = r"""
- name: Get all physical volumes
  aursu.general.lvm_info:
    filter: pvs
  register: lvm_pvs

- name: Get all volume groups
  aursu.general.lvm_info:
    filter: vgs
  register: lvm_vgs

- name: Get all logical volumes
  aursu.general.lvm_info:
    filter: lvs
  register: lvm_lvs

- name: Show all PV device paths
  debug:
    var: lvm_pvs.lvm.pvs | map(attribute='pv') | list

- name: Get all LVM information
  aursu.general.lvm_info:
    filter: all
  register: lvm_info

- name: Get volume groups and logical volumes
  aursu.general.lvm_info:
    filter: vgs,lvs
  register: lvm_info
"""

RETURN = r"""
pv:
  description: >
    List of physical volumes with details.
    This list is populated only when the 'filter' parameter is set to 'pvs' or not set at all.
    This list is also populated when the 'filter' parameter includes this type or is set to 'all'.
  returned: always
  type: list
  elements: dict
  sample:
    - pv_name: "/dev/sdb1"
      vg_name: "data"
      pv_fmt: "lvm2"
      pv_attr: "a--"
      pv_size: "<1.75t"
      pv_free: "158.49g"

vg:
  description: >
    List of volume groups with summary attributes.
    This list is populated only when the 'filter' parameter is set to 'vgs'.
    This list is also populated when the 'filter' parameter includes this type or is set to 'all'.
  returned: always
  type: list
  elements: dict
  sample:
    - vg_name: "data"
      pv_count: "1"
      lv_count: "10"
      snap_count: "0"
      vg_attr: "wz--n-"
      vg_size: "<1.75t"
      vg_free: "158.49g"

lv:
  description: >
    List of logical volumes with detailed attributes.
    This list is populated only when the 'filter' parameter is set to 'lvs'.
    This list is also populated when the 'filter' parameter includes this type or is set to 'all'.
  returned: always
  type: list
  elements: dict
  sample:
    - lv_name: "proj-test-data2"
      vg_name: "data"
      lv_attr: "-wi-a-----"
      lv_size: "209715200.00k"
      pool_lv: ""
      origin: ""
      data_percent: ""
      metadata_percent: ""
      move_pv: ""
      mirror_log: ""
      copy_percent: ""
      convert_lv: ""
"""

# LVM-supported unit suffixes, grouped by type

# Binary (base-2) units: lowercase
lvm_units_binary = ['b', 's', 'k', 'm', 'g', 't', 'p', 'e']

# Decimal (base-10 / SI) units: uppercase
lvm_units_decimal = ['B', 'S', 'K', 'M', 'G', 'T', 'P', 'E']

# Human-readable formats
lvm_units_human = ['r', 'R', 'h', 'H']

# All supported LVM units for --units argument
lvm_units = (
    lvm_units_binary +
    lvm_units_decimal +
    lvm_units_human
)

def get_lvm_status(module, lvm_exec, unit):
    """
    Fetches information about LVM and returns a dictionary.
    """

    command = [lvm_exec, "--units", unit, "--reportformat", "json"]

    rc, out, err = module.run_command(command)
    if rc != 0:
        module.fail_json(
          msg=f"Error while getting LVM information with {lvm_exec}",
          rc=rc, stdout=out, stderr=err
        )
    try:
        lvm_status = json.loads(out)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        module.fail_json(
            msg=f"Failed to parse JSON from {lvm_exec}",
            stdout=out,
            error=str(e)
        )

    return lvm_status.get("report", [{}])[0]

def main():
    module = AnsibleModule(
        argument_spec=dict(
            unit=dict(type='str', default='m', choices=lvm_units),
            filter=dict(type='raw', default='pvs'),
        ),
        supports_check_mode=True
    )
    module.run_command_environ_update = {'LANG': 'C', 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LC_CTYPE': 'C'}

    unit = module.params['unit']
    raw_filter = module.params['filter']

    if isinstance(raw_filter, str):
        if raw_filter == 'all':
            lvm_scopes = ['pvs', 'vgs', 'lvs']
        else:
            lvm_scopes = [s.strip() for s in raw_filter.split(',')]
    elif isinstance(raw_filter, list):
        lvm_scopes = raw_filter
    else:
        module.fail_json(msg="Invalid filter type, must be string or list")

    valid_scopes = {'pvs', 'vgs', 'lvs'}
    if not set(lvm_scopes).issubset(valid_scopes):
        module.fail_json(msg=f"Unsupported filter value(s): {lvm_scopes}")

    result = {'pv': [], 'vg': [], 'lv': []}
    for scope in lvm_scopes:
        lvm_exec = module.get_bin_path(scope, required=True)
        report = get_lvm_status(module, lvm_exec, unit)
        result.update({k: v for k, v in report.items() if k in ['pv', 'vg', 'lv']})

    module.exit_json(changed=False, **result)

if __name__ == '__main__':
    main()

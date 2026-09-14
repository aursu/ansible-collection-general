#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import unittest
from unittest.mock import MagicMock, patch

from ansible_collections.aursu.general.plugins.modules import fstab_info

MODULE_MOD = 'ansible_collections.aursu.general.plugins.modules.fstab_info'

# A real findmnt --fstab -J payload, taken verbatim from a host whose volume
# group had been renamed: the source no longer exists, and the options lack
# nofail. Both facts are visible only in the static table.
STALE_ENTRY = {
    "target": "/mnt/disks/data1",
    "source": "/dev/data-ssd/data1",
    "fstype": "xfs",
    "options": "defaults",
    "freq": 0,
    "passno": 0,
}

ROOT_ENTRY = {
    "target": "/",
    "source": "UUID=b450d575-c6b6-4963-9919-49b1c53cad47",
    "fstype": "ext4",
    "options": "rw,relatime",
    "freq": 0,
    "passno": 1,
}


def fake_module(rc=0, stdout="", stderr=""):
    """An AnsibleModule stand-in that records the command it was given."""
    module = MagicMock()
    module.run_command.return_value = (rc, stdout, stderr)
    return module


class TestRunFindmntFstab(unittest.TestCase):
    """The helper that reads the static table."""

    def test_parses_the_filesystems_array(self):
        module = fake_module(stdout=json.dumps({"filesystems": [ROOT_ENTRY, STALE_ENTRY]}))
        entries = fstab_info.run_findmnt_fstab(module)
        self.assertEqual(entries, [ROOT_ENTRY, STALE_ENTRY])

    def test_reads_fstab_not_the_live_table(self):
        module = fake_module(stdout=json.dumps({"filesystems": []}))
        fstab_info.run_findmnt_fstab(module)
        command = module.run_command.call_args[0][0]
        self.assertIn('--fstab', command)
        self.assertIn('-J', command)

    def test_asks_for_an_explicit_column_set(self):
        # Left to the util-linux default, the output shape drifts between
        # releases and the parsed keys change underneath callers.
        module = fake_module(stdout=json.dumps({"filesystems": []}))
        fstab_info.run_findmnt_fstab(module)
        command = module.run_command.call_args[0][0]
        self.assertIn('-o', command)
        self.assertEqual(command[command.index('-o') + 1], fstab_info.FSTAB_COLUMNS)
        for column in ('TARGET', 'SOURCE', 'FSTYPE', 'OPTIONS'):
            self.assertIn(column, fstab_info.FSTAB_COLUMNS)

    def test_filters_by_mountpoint_not_by_device(self):
        # The point of the module: a stale source cannot be resolved back to a
        # device, so a device-keyed lookup finds nothing for exactly the broken
        # entries. Matching on the target always works.
        module = fake_module(stdout=json.dumps({"filesystems": [STALE_ENTRY]}))
        fstab_info.run_findmnt_fstab(module, "/mnt/disks/data1")
        command = module.run_command.call_args[0][0]
        self.assertIn('--mountpoint', command)
        self.assertEqual(command[command.index('--mountpoint') + 1], "/mnt/disks/data1")

    def test_no_mountpoint_filter_when_path_is_omitted(self):
        module = fake_module(stdout=json.dumps({"filesystems": []}))
        fstab_info.run_findmnt_fstab(module)
        self.assertNotIn('--mountpoint', module.run_command.call_args[0][0])


class TestNoMatchIsNotAnError(unittest.TestCase):
    """findmnt exits 1 when nothing matched. That is a state, not a failure."""

    def test_exit_one_yields_an_empty_list(self):
        module = fake_module(rc=1, stdout="")
        self.assertEqual(fstab_info.run_findmnt_fstab(module, "/not/in/fstab"), [])

    def test_empty_stdout_yields_an_empty_list(self):
        self.assertEqual(fstab_info.run_findmnt_fstab(fake_module(stdout="   ")), [])

    def test_unparseable_output_yields_an_empty_list(self):
        self.assertEqual(fstab_info.run_findmnt_fstab(fake_module(stdout="not json")), [])

    def test_missing_filesystems_key_yields_an_empty_list(self):
        module = fake_module(stdout=json.dumps({"something_else": []}))
        self.assertEqual(fstab_info.run_findmnt_fstab(module), [])


class TestMain(unittest.TestCase):
    """The module's return contract."""

    def _run(self, params, exists=True, entries=None, rc=0):
        payload = json.dumps({"filesystems": entries if entries is not None else []})
        with patch(f'{MODULE_MOD}.AnsibleModule') as ansible_module, \
             patch(f'{MODULE_MOD}.os.path.exists', return_value=exists):
            instance = MagicMock()
            instance.params = params
            instance.run_command.return_value = (rc, payload, "")
            ansible_module.return_value = instance
            fstab_info.main()
            return instance.exit_json.call_args

    def test_entry_is_returned_when_a_path_matches(self):
        call = self._run({"path": "/mnt/disks/data1"}, entries=[STALE_ENTRY])
        result = call.kwargs
        self.assertEqual(result["entry"], STALE_ENTRY)
        self.assertEqual(result["fstab"], [STALE_ENTRY])
        self.assertTrue(result["is_exists"])
        self.assertFalse(call.kwargs["changed"])

    def test_entry_is_none_when_the_mountpoint_is_not_declared(self):
        # Distinguishable from "mounted correctly": the caller must be able to
        # tell an absent fstab line from a correct one.
        result = self._run({"path": "/mnt/disks/data1"}, entries=[]).kwargs
        self.assertIsNone(result["entry"])
        self.assertEqual(result["fstab"], [])

    def test_entry_stays_none_when_no_path_was_requested(self):
        result = self._run({"path": None}, entries=[ROOT_ENTRY, STALE_ENTRY]).kwargs
        self.assertIsNone(result["entry"])
        self.assertEqual(len(result["fstab"]), 2)

    def test_missing_fstab_reports_is_exists_false(self):
        result = self._run({"path": None}, exists=False).kwargs
        self.assertFalse(result["is_exists"])
        self.assertEqual(result["fstab"], [])
        self.assertIsNone(result["entry"])

    def test_the_module_never_reports_a_change(self):
        # It is an information module; reporting changed would make every play
        # that uses it look like it modified the host.
        for params in ({"path": None}, {"path": "/mnt/disks/data1"}):
            call = self._run(params, entries=[STALE_ENTRY])
            self.assertFalse(call.kwargs["changed"])


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

import unittest
import io
from unittest.mock import patch
from ansible_collections.aursu.general.plugins.modules.sshd_info import SshConfigParser, OptionStore

TARGET_MOD = 'ansible_collections.aursu.general.plugins.modules.sshd_info'

class TestOptionStore(unittest.TestCase):
    def test_first_match_wins(self):
        """
        Verify that the first value is retained as effective, and subsequent
        values are recorded in the appearance list.
        """
        store = OptionStore("global")

        # 1. First occurrence
        store.add("Port", "22", "/etc/ssh/sshd_config")

        # 2. Second occurrence (shadowing)
        store.add("Port", "2222", "/etc/ssh/conf.d/override.conf")

        data = store.to_dict()

        self.assertEqual(data["Port"]["value"], "22")
        self.assertEqual(len(data["Port"]["appearance"]), 2)
        self.assertEqual(data["Port"]["appearance"][0], "/etc/ssh/sshd_config")
        self.assertEqual(data["Port"]["appearance"][1], "/etc/ssh/conf.d/override.conf")

    def test_structure_format(self):
        """Verify that Match block returns correct condition field."""
        store = OptionStore("User bob")
        store.update_appearance("/etc/ssh/sshd_config")
        store.add("X11Forwarding", "yes", "/etc/ssh/sshd_config")

        data = store.to_dict()

        # ИСПРАВЛЕНО: проверяем condition, так как в коде используется этот ключ
        self.assertEqual(data["condition"], "User bob")
        self.assertEqual(data["location"], "/etc/ssh/sshd_config")
        self.assertIn("X11Forwarding", data["options"])

class TestSshConfigParser(unittest.TestCase):
    def setUp(self):
        self.parser = SshConfigParser()
        self.fs_map = {}

    def _mock_reader(self, filename, *args, **kwargs):
        if filename in self.fs_map:
            return io.StringIO(self.fs_map[filename])
        raise IOError(f"File not found: {filename}")

    @patch(f'{TARGET_MOD}.io.open')
    @patch(f'{TARGET_MOD}.glob.glob')
    @patch(f'{TARGET_MOD}.os.path.isfile')
    @patch(f'{TARGET_MOD}.os.path.exists')
    def test_global_and_include(self, mock_exists, mock_isfile, mock_glob, mock_io_open):
        """Global option + Include containing overrides."""
        mock_exists.return_value = True
        mock_isfile.return_value = True

        self.fs_map = {
            "/etc/ssh/sshd_config": "Port 22\nInclude /etc/ssh/extra.conf\n",
            "/etc/ssh/extra.conf": "Port 80\nPermitRootLogin no\n"
        }

        mock_glob.side_effect = lambda x: [x] if x in self.fs_map else []
        mock_io_open.side_effect = self._mock_reader

        self.parser.parse("/etc/ssh/sshd_config")
        result = self.parser.get_structured_data()

        self.assertEqual(result["Port"]["value"], "22")
        self.assertEqual(result["Port"]["location"], "/etc/ssh/sshd_config")
        self.assertEqual(result["Port"]["appearance"], ["/etc/ssh/sshd_config", "/etc/ssh/extra.conf"])
        self.assertEqual(result["PermitRootLogin"]["value"], "no")

    @patch(f'{TARGET_MOD}.io.open')
    @patch(f'{TARGET_MOD}.glob.glob')
    @patch(f'{TARGET_MOD}.os.path.isfile')
    @patch(f'{TARGET_MOD}.os.path.exists')
    def test_match_merging_and_scope(self, mock_exists, mock_isfile, mock_glob, mock_io_open):
        """Merging Match blocks from different files."""
        mock_exists.return_value = True
        mock_isfile.return_value = True

        self.fs_map = {
            "/main": "Match User bob\nBanner one\nInclude /extra\n",
            "/extra": "Match User bob\nBanner two\nX11Forwarding yes\n"
        }

        mock_glob.side_effect = lambda x: [x] if x in self.fs_map else []
        mock_io_open.side_effect = self._mock_reader

        self.parser.parse("/main")
        result = self.parser.get_structured_data()

        matches = result["Match"]
        self.assertEqual(len(matches), 1)
        bob_block = matches[0]

        # ИСПРАВЛЕНО: проверяем condition
        self.assertEqual(bob_block["condition"], "User bob")
        self.assertEqual(bob_block["location"], "/main")
        self.assertEqual(bob_block["appearance"], ["/main", "/extra"])
        self.assertEqual(bob_block["options"]["Banner"]["value"], "one")
        self.assertEqual(bob_block["options"]["Banner"]["location"], "/main")
        self.assertEqual(bob_block["options"]["Banner"]["appearance"], ["/main", "/extra"])
        self.assertEqual(bob_block["options"]["X11Forwarding"]["value"], "yes")
        self.assertEqual(bob_block["options"]["X11Forwarding"]["location"], "/extra")

    @patch(f'{TARGET_MOD}.io.open')
    @patch(f'{TARGET_MOD}.glob.glob')
    @patch(f'{TARGET_MOD}.os.path.isfile')
    @patch(f'{TARGET_MOD}.os.path.exists')
    def test_match_all_reset(self, mock_exists, mock_isfile, mock_glob, mock_io_open):
        """'Match All' should reset scope to global."""
        mock_exists.return_value = True
        mock_isfile.return_value = True

        self.fs_map = {
            "/sshd": "Match User bob\nPermitRootLogin yes\nMatch All\nMaxAuthTries 3\n"
        }

        mock_glob.side_effect = lambda x: [x] if x in self.fs_map else []
        mock_io_open.side_effect = self._mock_reader

        self.parser.parse("/sshd")
        result = self.parser.get_structured_data()

        # Global scope check
        self.assertIn("MaxAuthTries", result)
        self.assertEqual(result["MaxAuthTries"]["value"], "3")

        # Match scope check
        matches = result["Match"]
        self.assertEqual(len(matches), 1)
        bob_block = matches[0]

        self.assertNotIn("PermitRootLogin", result)
        self.assertEqual(bob_block["options"]["PermitRootLogin"]["value"], "yes")

    @patch(f'{TARGET_MOD}.io.open')
    @patch(f'{TARGET_MOD}.glob.glob')
    @patch(f'{TARGET_MOD}.os.path.isfile')
    @patch(f'{TARGET_MOD}.os.path.exists')
    def test_loop_protection(self, mock_exists, mock_isfile, mock_glob, mock_io_open):
        """Circular includes (A -> B -> A)."""
        mock_exists.return_value = True
        mock_isfile.return_value = True

        self.fs_map = {
            "/A": "Include /B\nVarA 1",
            "/B": "Include /A\nVarB 1"
        }
        mock_glob.side_effect = lambda x: [x] if x in self.fs_map else []
        mock_io_open.side_effect = self._mock_reader

        try:
            self.parser.parse("/A")
        except RecursionError:
            self.fail("Parser failed with RecursionError on circular includes")

        result = self.parser.get_structured_data()

        self.assertEqual(result["VarA"]["value"], "1")
        self.assertEqual(result["VarB"]["value"], "1")

if __name__ == '__main__':
    unittest.main()

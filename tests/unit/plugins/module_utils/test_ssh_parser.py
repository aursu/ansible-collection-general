#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

import unittest
import io
from unittest.mock import patch
from ansible_collections.aursu.general.plugins.module_utils.ssh_parser import SshConfigParser, OptionStore

TARGET_MOD = 'ansible_collections.aursu.general.plugins.module_utils.ssh_parser'

class TestOptionStore(unittest.TestCase):
    def test_first_match_wins(self):
        """
        Verify that the first value is retained as effective, and subsequent
        values are recorded in the appearance list.
        """
        store = OptionStore("global")

        # MaxAuthTries is shadowed. Port is deliberately NOT used here: it is
        # cumulative, so it would not demonstrate shadowing at all.
        # 1. First occurrence
        store.add("MaxAuthTries", "3", "/etc/ssh/sshd_config")

        # 2. Second occurrence (shadowing)
        store.add("MaxAuthTries", "9", "/etc/ssh/conf.d/override.conf")

        data = store.to_dict()

        self.assertEqual(data["MaxAuthTries"]["value"], "3")
        self.assertEqual(len(data["MaxAuthTries"]["appearance"]), 2)
        self.assertEqual(data["MaxAuthTries"]["appearance"][0], "/etc/ssh/sshd_config")
        self.assertEqual(data["MaxAuthTries"]["appearance"][1], "/etc/ssh/conf.d/override.conf")

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
            "/etc/ssh/sshd_config": "MaxAuthTries 3\nInclude /etc/ssh/extra.conf\n",
            "/etc/ssh/extra.conf": "MaxAuthTries 9\nPermitRootLogin no\n"
        }

        mock_glob.side_effect = lambda x: [x] if x in self.fs_map else []
        mock_io_open.side_effect = self._mock_reader

        self.parser.parse("/etc/ssh/sshd_config")
        result = self.parser.get_structured_data()

        self.assertEqual(result["MaxAuthTries"]["value"], "3")
        self.assertEqual(result["MaxAuthTries"]["location"], "/etc/ssh/sshd_config")
        self.assertEqual(result["MaxAuthTries"]["appearance"], ["/etc/ssh/sshd_config", "/etc/ssh/extra.conf"])
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


class TestMalformedMatch:
    """`Match` with no condition. sshd rejects it outright:

        sshd -t: line 1: no argument after keyword "Match"

    The parser used to take the empty value as a scope name, silently creating a
    scope called "" and filing every following option under it. A configuration
    sshd refuses to load should not parse into something plausible-looking.
    """

    def test_bare_match_is_recorded_as_an_error(self, tmp_path):
        cfg = tmp_path / "sshd_config"
        cfg.write_text("Port 22\nMatch\nX11Forwarding yes\n", encoding="utf-8")
        parser = SshConfigParser(base_dir=str(tmp_path))
        parser.parse(str(cfg), "global")
        assert any("Match" in e["reason"] for e in parser.errors)

    def test_bare_match_creates_no_empty_scope(self, tmp_path):
        cfg = tmp_path / "sshd_config"
        cfg.write_text("Port 22\nMatch\nX11Forwarding yes\n", encoding="utf-8")
        parser = SshConfigParser(base_dir=str(tmp_path))
        parser.parse(str(cfg), "global")
        assert "" not in parser.registry, "an empty scope name must never be created"


class TestParseReturnValue:
    """parse() reports whether it got through cleanly, so a caller need not
    introspect .errors to find out."""

    def test_true_on_a_clean_parse(self, tmp_path):
        cfg = tmp_path / "sshd_config"
        cfg.write_text("Port 22\n", encoding="utf-8")
        assert SshConfigParser(base_dir=str(tmp_path)).parse(str(cfg), "global") is True

    def test_false_when_the_file_is_missing(self, tmp_path):
        assert SshConfigParser(base_dir=str(tmp_path)).parse(
            str(tmp_path / "nope"), "global") is False

    def test_false_when_a_line_cannot_be_parsed(self, tmp_path):
        cfg = tmp_path / "sshd_config"
        cfg.write_text('Port 22\nBanner "/etc/unclosed\n', encoding="utf-8")
        assert SshConfigParser(base_dir=str(tmp_path)).parse(str(cfg), "global") is False

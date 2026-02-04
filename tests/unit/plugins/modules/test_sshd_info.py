#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import unittest
import io
from unittest.mock import MagicMock, patch
from ansible_collections.aursu.general.plugins.modules import sshd_info

# Patching paths (must patch at the location where the dependency is used).
# Since sshd_info imports SshConfigParser, which uses io and os internally,
# we need to patch dependencies inside module_utils.
PARSER_MOD = 'ansible_collections.aursu.general.plugins.module_utils.ssh_parser'
MODULE_MOD = 'ansible_collections.aursu.general.plugins.modules.sshd_info'

class TestSshdInfoIntegration(unittest.TestCase):

    def setUp(self):
        # Virtual filesystem for testing
        # Use u"" for compatibility
        self.fs_map = {
            "/etc/ssh/sshd_config": u"""
Port 22
Include /etc/ssh/conf.d/*.conf
Match User bob
    X11Forwarding yes
""",
            "/etc/ssh/conf.d/01-custom.conf": u"""
PasswordAuthentication no
Port 2222
"""
        }
        # 2. Patch initialization
        # Helper _apply_patch is used to avoid repetitive patching code
        self.mock_abspath = self._apply_patch(f'{PARSER_MOD}.os.path.abspath')
        self.mock_glob = self._apply_patch(f'{PARSER_MOD}.glob.glob')
        self.mock_exists_parser = self._apply_patch(f'{PARSER_MOD}.os.path.exists')
        self.mock_isfile_parser = self._apply_patch(f'{PARSER_MOD}.os.path.isfile')
        self.mock_io_open = self._apply_patch(f'{PARSER_MOD}.io.open')

        self.mock_exists_module = self._apply_patch(f'{MODULE_MOD}.os.path.exists')
        self.mock_ansible_module = self._apply_patch(f'{MODULE_MOD}.AnsibleModule')

        # 3. Configure side effects

        # Abspath: returns the path as is
        self.mock_abspath.side_effect = lambda x: x

        # File reader
        self.mock_io_open.side_effect = self._mock_reader

        # Glob emulation
        self.mock_glob.side_effect = self._mock_glob

        # Existence checks (Parser + Module + IsFile)
        # For simplicity: everything in the map is considered an existing file
        check_exists = lambda x: x in self.fs_map
        self.mock_exists_parser.side_effect = check_exists
        self.mock_isfile_parser.side_effect = check_exists
        self.mock_exists_module.side_effect = check_exists

        # 4. Configure AnsibleModule
        self.mock_module_instance = MagicMock()
        self.mock_module_instance.params = {'config_path': '/etc/ssh/sshd_config'}
        self.mock_ansible_module.return_value = self.mock_module_instance

    def _apply_patch(self, target):
        """Applies a patch and ensures it is stopped after the test"""
        patcher = patch(target)
        mock_obj = patcher.start()
        self.addCleanup(patcher.stop)
        return mock_obj

    def _mock_reader(self, filename, *args, **kwargs):
        if filename in self.fs_map:
            return io.StringIO(self.fs_map[filename])
        raise IOError(f"File not found in mock fs: {filename}")

    def _mock_glob(self, pattern):
        if pattern == "/etc/ssh/conf.d/*.conf":
            return ["/etc/ssh/conf.d/01-custom.conf"]
        return [pattern] if pattern in self.fs_map else []

    def test_full_parsing_logic(self):
        # 1. Запуск
        sshd_info.main()

        # 2. Проверки
        if self.mock_module_instance.fail_json.called:
            self.fail(f"Module failed: {self.mock_module_instance.fail_json.call_args}")

        self.mock_module_instance.exit_json.assert_called_once()
        args, kwargs = self.mock_module_instance.exit_json.call_args
        result = kwargs.get('sshd_config')

        self.assertIsNotNone(result)
        self.assertIn('Port', result, "Parser returned empty result")

        # Проверка значений
        self.assertEqual(result['Port']['value'], '22')
        self.assertEqual(result['Port']['location'], '/etc/ssh/sshd_config')
        self.assertEqual(result['PasswordAuthentication']['value'], 'no')

        match_block = result['Match'][0]
        self.assertEqual(match_block['condition'], 'User bob')
        self.assertEqual(match_block['options']['X11Forwarding']['value'], 'yes')

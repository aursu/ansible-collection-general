#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import unittest
from unittest.mock import MagicMock, patch

from ansible_collections.aursu.general.plugins.modules import kernel_info

MODULE_MOD = 'ansible_collections.aursu.general.plugins.modules.kernel_info'

DPKG_QUERY = (
    'linux-image-6.17.0-35-generic\tii \n'
    'linux-modules-6.17.0-35-generic\tii \n'
    'linux-image-7.0.0-43-generic\tii \n'
    'linux-base\tii \n'
)


class TestMain(unittest.TestCase):
    """The module's return contract; the inventory itself is tested in test_kernels."""

    def _run(self, release='7.0.0-43-generic'):
        with patch(f'{MODULE_MOD}.AnsibleModule') as ansible_module, \
             patch(f'{MODULE_MOD}.os.uname', return_value=('Linux', 'h', release, '', 'x86_64')):
            instance = MagicMock()
            instance.params = {'boot_dir': '/nonexistent-boot'}
            instance.get_bin_path.return_value = '/usr/bin/dpkg-query'
            instance.run_command.return_value = (0, DPKG_QUERY, '')
            ansible_module.return_value = instance
            kernel_info.main()
            return instance.exit_json.call_args.kwargs

    def test_returns_the_inventory_and_the_running_release(self):
        result = self._run()
        self.assertEqual(result['running_release'], '7.0.0-43-generic')
        self.assertEqual([k['version'] for k in result['installed_kernels']], ['6.17.0-35', '7.0.0-43'])
        self.assertEqual(result['installed_kernels'][0]['packages'],
                         ['linux-image-6.17.0-35-generic', 'linux-modules-6.17.0-35-generic'])

    def test_running_comes_from_uname(self):
        kernels = self._run(release='6.17.0-35-generic')['installed_kernels']
        self.assertEqual([k['running'] for k in kernels], [True, False])

    def test_the_module_never_reports_a_change(self):
        self.assertFalse(self._run()['changed'])


if __name__ == '__main__':
    unittest.main()

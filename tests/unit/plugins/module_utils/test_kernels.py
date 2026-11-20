#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from ansible_collections.aursu.general.plugins.module_utils.kernels import DebianKernelInventory

# Real `dpkg-query -W -f '${Package}\t${db:Status-Abbrev}\n' 'linux-*'` output
# from an Ubuntu 24.04 HWE host with four kernels, two kernel series, 14
# not-installed (`un`) names and one package with only config files (`rc`).
FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'dpkg_query_ubuntu2404_hwe.txt')
with open(FIXTURE) as handle:
    DPKG_QUERY = handle.read()


def fake_module(rc=0, stdout=DPKG_QUERY, stderr=""):
    module = MagicMock()
    module.get_bin_path.return_value = '/usr/bin/dpkg-query'
    module.run_command.return_value = (rc, stdout, stderr)
    module.fail_json.side_effect = SystemExit
    return module


class TestParse(unittest.TestCase):
    """Grouping packages into kernels, on the real fixture."""

    def setUp(self):
        self.kernels = {k.version: k for k in DebianKernelInventory.parse(DPKG_QUERY)}

    def test_four_kernels_oldest_first(self):
        versions = [k.version for k in DebianKernelInventory.parse(DPKG_QUERY)]
        self.assertEqual(versions, ['6.17.0-14', '6.17.0-20', '6.17.0-35', '7.0.0-43'])

    def test_all_packages_of_a_kernel_are_found(self):
        self.assertEqual(sorted(self.kernels['6.17.0-14'].packages), [
            'linux-headers-6.17.0-14-generic',
            'linux-hwe-6.17-headers-6.17.0-14',
            'linux-hwe-6.17-tools-6.17.0-14',
            'linux-image-6.17.0-14-generic',
            'linux-modules-6.17.0-14-generic',
            'linux-modules-extra-6.17.0-14-generic',
            'linux-tools-6.17.0-14-generic',
        ])

    def test_packages_new_to_a_kernel_series_are_found(self):
        # 7.0 adds linux-main-modules-* and drops linux-modules-extra; a list of
        # known prefixes written for 6.17 would miss the first and expect the second.
        packages = self.kernels['7.0.0-43'].packages
        self.assertIn('linux-main-modules-zfs-7.0.0-43-generic', packages)
        self.assertIn('linux-main-modules-v4l2loopback-7.0.0-43-generic', packages)
        self.assertNotIn('linux-modules-extra-7.0.0-43-generic', packages)

    def test_release_is_what_uname_reports(self):
        self.assertEqual(self.kernels['7.0.0-43'].releases, ['7.0.0-43-generic'])

    def test_meta_shared_and_firmware_packages_belong_to_no_kernel(self):
        every = [p for k in self.kernels.values() for p in k.packages]
        for name in ('linux-generic-hwe-24.04', 'linux-image-generic-hwe-24.04', 'linux-base',
                     'linux-firmware', 'linux-libc-dev', 'linux-tools-common'):
            self.assertNotIn(name, every)

    def test_not_installed_and_config_only_packages_are_skipped(self):
        every = [p for k in self.kernels.values() for p in k.packages]
        self.assertNotIn('linux-image-unsigned-7.0.0-43-generic', every)   # un
        # 3 x 7 for the 6.17 kernels + 8 for 7.0.0-43, out of 69 lines.
        self.assertEqual(len(every), 29)

    def test_half_configured_package_still_counts(self):
        kernels = DebianKernelInventory.parse('linux-image-6.17.0-35-generic\tiF \n')
        self.assertEqual(kernels[0].packages, ['linux-image-6.17.0-35-generic'])

    def test_version_order_is_numeric(self):
        text = 'linux-image-6.17.0-14-generic\tii \nlinux-image-6.17.0-9-generic\tii \n'
        self.assertEqual([k.version for k in DebianKernelInventory.parse(text)], ['6.17.0-9', '6.17.0-14'])

    def test_leftover_packages_without_an_image_are_not_bootable(self):
        kernels = DebianKernelInventory.parse('linux-hwe-6.17-headers-6.17.0-14\tii \n')
        self.assertFalse(kernels[0].has_image)


class TestCollect(unittest.TestCase):
    """Running, latest and the /boot footprint."""

    def setUp(self):
        self.boot = tempfile.mkdtemp()
        for name, size in (('vmlinuz-6.17.0-35-generic', 100), ('initrd.img-6.17.0-35-generic', 1000),
                           ('System.map-6.17.0-35-generic', 10), ('config-6.17.0-35-generic', 1),
                           ('initrd.img-6.17.0-35-generic.bak', 5000)):
            with open(os.path.join(self.boot, name), 'wb') as handle:
                handle.write(b'x' * size)

    def tearDown(self):
        shutil.rmtree(self.boot)

    def collect(self, running='7.0.0-43-generic', **module_kwargs):
        inventory = DebianKernelInventory(fake_module(**module_kwargs), boot_dir=self.boot)
        return {k['version']: k for k in inventory.collect(running_release=running)}

    def test_running_and_latest(self):
        kernels = self.collect()
        self.assertEqual([v for v, k in kernels.items() if k['running']], ['7.0.0-43'])
        self.assertEqual([v for v, k in kernels.items() if k['latest']], ['7.0.0-43'])

    def test_running_kernel_need_not_be_the_latest(self):
        kernels = self.collect(running='6.17.0-35-generic')
        self.assertTrue(kernels['6.17.0-35']['running'])
        self.assertFalse(kernels['6.17.0-35']['latest'])

    def test_boot_bytes_count_only_the_kernel_files(self):
        self.assertEqual(self.collect()['6.17.0-35']['boot_bytes'], 1111)
        self.assertEqual(self.collect()['6.17.0-14']['boot_bytes'], 0)

    def test_no_kernel_packages_is_an_empty_inventory(self):
        # dpkg-query exits 1 with no output when the pattern matches nothing.
        self.assertEqual(self.collect(rc=1, stdout=''), {})

    def test_any_other_failure_fails_the_module(self):
        with self.assertRaises(SystemExit):
            self.collect(rc=2, stdout='', stderr='dpkg-query: error')


if __name__ == '__main__':
    unittest.main()

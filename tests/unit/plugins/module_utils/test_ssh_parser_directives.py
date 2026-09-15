#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error

"""Directive-level behaviour: the equals form, and repeated directives.

The expectations here are not taken from the sshd_config man page but measured
against OpenSSH 9.9p1 with `sshd -T`, by writing a config with two occurrences
of a directive and reading back what the daemon computed. That matters because
the intuition is wrong in both directions: Port and AllowUsers accumulate, while
SetEnv, PermitOpen and PermitListen do not.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os

import pytest

from ansible_collections.aursu.general.plugins.module_utils.ssh_parser import (
    CUMULATIVE_DIRECTIVES,
    SshConfigParser,
    split_directive,
)


def parse(tmp_path, main, includes=None):
    """Write a config tree to disk and parse it for real."""
    base = tmp_path / "ssh"
    base.mkdir(exist_ok=True)
    (base / "sshd_config").write_text(main)

    if includes:
        dropin = base / "sshd_config.d"
        dropin.mkdir(exist_ok=True)
        for name, body in includes.items():
            (dropin / name).write_text(body)

    parser = SshConfigParser(base_dir=str(base))
    parser.parse(str(base / "sshd_config"))
    return parser, parser.get_structured_data()


class TestSplitDirective:
    @pytest.mark.parametrize("line, expected", [
        ("Port 22", ("Port", "22")),
        ("PermitRootLogin=prohibit-password", ("PermitRootLogin", "prohibit-password")),
        ("MaxAuthTries = 5", ("MaxAuthTries", "5")),
        ("MaxAuthTries=5", ("MaxAuthTries", "5")),
        ("AllowUsers alice bob", ("AllowUsers", "alice bob")),
        ("Subsystem sftp /usr/libexec/sftp-server", ("Subsystem", "sftp /usr/libexec/sftp-server")),
        ("Banner  none", ("Banner", "none")),
        ('AuthorizedKeysFile "/etc/ssh/keys/%u"', ("AuthorizedKeysFile", "/etc/ssh/keys/%u")),
        ("PermitRootLogin", ("PermitRootLogin", "")),
    ])
    def test_accepted_spellings(self, line, expected):
        assert split_directive(line) == expected

    def test_unbalanced_quotes_are_reported_not_guessed(self):
        assert split_directive('Banner "unterminated') == (None, None)

    def test_empty_line(self):
        assert split_directive("") == (None, None)


class TestCumulativeDirectives:
    """Directives where every occurrence takes effect."""

    @pytest.mark.parametrize("directive, a, b", [
        ("Port", "22", "2222"),
        ("ListenAddress", "127.0.0.1", "127.0.0.2"),
        ("HostKey", "/etc/ssh/rsa", "/etc/ssh/ed25519"),
        ("AllowUsers", "alice", "bob"),
        ("DenyUsers", "carol", "dave"),
        ("AllowGroups", "one", "two"),
        ("DenyGroups", "three", "four"),
        ("AcceptEnv", "LANG", "LC_ALL"),
    ])
    def test_every_occurrence_is_kept(self, tmp_path, directive, a, b):
        _, data = parse(tmp_path, "%s %s\n%s %s\n" % (directive, a, directive, b))
        entry = data[directive]
        assert entry["cumulative"] is True
        # One field for the setting: a list, because all of them are in force.
        assert entry["value"] == [a, b]
        assert "values" not in entry


    def test_a_single_occurrence_is_still_a_list(self, tmp_path):
        # The type follows the flag, not the count. A cumulative directive
        # written once still yields a one-item list, so a caller never has to
        # handle both shapes for the same directive.
        _, data = parse(tmp_path, "Port 22\n")
        entry = data["Port"]
        assert entry["cumulative"] is True
        assert entry["value"] == ["22"]

    def test_listenaddress_is_the_one_that_matters_for_binding(self, tmp_path):
        # A host bound to two internal addresses must not be reported as bound
        # to one; that reads as a narrower exposure than is actually configured.
        _, data = parse(tmp_path, "ListenAddress 10.0.0.1\nListenAddress 10.0.0.2\n")
        assert data["ListenAddress"]["value"] == ["10.0.0.1", "10.0.0.2"]


class TestShadowedDirectives:
    """Directives where the first wins and the rest are silently discarded."""

    def test_first_wins_and_nothing_else_is_reported(self, tmp_path):
        _, data = parse(tmp_path, "PasswordAuthentication no\nPasswordAuthentication yes\n")
        entry = data["PasswordAuthentication"]
        assert entry["value"] == "no"
        # The shape is exactly three keys. The discarded "yes" is deliberately
        # not recorded: `appearance` already names the file to remove it from,
        # which is the actionable half.
        assert set(entry) == {"value", "location", "appearance"}

    @pytest.mark.parametrize("directive", ["SetEnv", "PermitOpen", "PermitListen"])
    def test_measured_non_cumulative_directives(self, directive):
        # Verified against sshd -T: these look like they should accumulate and
        # do not.
        assert directive.lower() not in CUMULATIVE_DIRECTIVES

    def test_repeats_in_one_file_do_not_inflate_appearance(self, tmp_path):
        # appearance is a list of FILES, de-duplicated - not a count of
        # occurrences. Two writes in one file are one entry.
        _, data = parse(tmp_path, "MaxAuthTries 3\nMaxAuthTries 9\n")
        entry = data["MaxAuthTries"]
        assert entry["value"] == "3"
        assert len(entry["appearance"]) == 1


class TestLocationAndAppearance:
    """The two fields a writer acts on."""

    def test_location_is_the_file_to_edit(self, tmp_path):
        parser, data = parse(
            tmp_path,
            "Include sshd_config.d/*.conf\nPasswordAuthentication yes\n",
            {"50-cloud-init.conf": "PasswordAuthentication no\n"},
        )
        entry = data["PasswordAuthentication"]
        # The drop-in is read first, so it wins - the scenario that makes
        # cloud-init quietly beat a hand-written sshd_config.
        assert entry["value"] == "no"
        assert entry["location"].endswith("50-cloud-init.conf")
        assert parser.errors == []

    def test_appearance_is_the_cleanup_list(self, tmp_path):
        # Every file the directive occurs in, winner first, in encounter order.
        _, data = parse(
            tmp_path,
            "Include sshd_config.d/*.conf\nPasswordAuthentication yes\n",
            {"50-cloud-init.conf": "PasswordAuthentication no\n"},
        )
        appearance = data["PasswordAuthentication"]["appearance"]
        assert len(appearance) == 2
        assert appearance[0].endswith("50-cloud-init.conf")
        assert appearance[1].endswith("sshd_config")
        # The contract a writer relies on: edit appearance[0], clean the rest.
        assert appearance[0] == data["PasswordAuthentication"]["location"]
class TestDiagnostics:
    """A short answer must not be indistinguishable from a correct one."""

    def test_parsed_files_lists_what_was_read_in_order(self, tmp_path):
        parser, _ = parse(
            tmp_path,
            "Include sshd_config.d/*.conf\nPort 22\n",
            {"10-a.conf": "Banner none\n", "20-b.conf": "MaxAuthTries 3\n"},
        )
        names = [os.path.basename(p) for p in parser.parsed_files]
        assert names == ["sshd_config", "10-a.conf", "20-b.conf"]

    def test_a_missing_config_is_reported(self, tmp_path):
        parser = SshConfigParser(base_dir=str(tmp_path))
        parser.parse(str(tmp_path / "nope"))
        assert len(parser.errors) == 1
        assert "does not exist" in parser.errors[0]["reason"]

    def test_a_directory_given_as_a_config_is_reported(self, tmp_path):
        parser = SshConfigParser(base_dir=str(tmp_path))
        parser.parse(str(tmp_path))
        assert any("not a regular file" in e["reason"] for e in parser.errors)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can read a 0000 file")
    def test_an_unreadable_dropin_is_reported_not_skipped(self, tmp_path):
        # Drop-ins are routinely 0600. Running unprivileged must not silently
        # yield a configuration with fewer options in it.
        parser, _ = parse(
            tmp_path,
            "Include sshd_config.d/*.conf\n",
            {"50-secret.conf": "PermitRootLogin yes\n"},
        )
        secret = tmp_path / "ssh" / "sshd_config.d" / "50-secret.conf"
        os.chmod(str(secret), 0o000)

        parser2 = SshConfigParser(base_dir=str(tmp_path / "ssh"))
        parser2.parse(str(tmp_path / "ssh" / "sshd_config"))
        assert any("could not be read" in e["reason"] for e in parser2.errors)

    def test_an_include_loop_is_reported_and_does_not_hang(self, tmp_path):
        base = tmp_path / "ssh"
        base.mkdir()
        (base / "sshd_config").write_text("Include %s/b.conf\nPort 22\n" % base)
        (base / "b.conf").write_text("Include %s/sshd_config\nBanner none\n" % base)

        parser = SshConfigParser(base_dir=str(base))
        parser.parse(str(base / "sshd_config"))
        data = parser.get_structured_data()

        assert data["Port"]["value"] == ["22"]
        assert any("loop" in e["reason"] for e in parser.errors)

    def test_an_unlexable_line_is_reported_with_its_number(self, tmp_path):
        parser, data = parse(tmp_path, 'Port 22\nBanner "unterminated\nMaxAuthTries 3\n')
        # Parsing continues past the bad line.
        assert data["Port"]["value"] == ["22"]
        assert data["MaxAuthTries"]["value"] == "3"
        assert any("line 2" in e["reason"] for e in parser.errors)

    def test_a_clean_parse_reports_no_errors(self, tmp_path):
        parser, _ = parse(tmp_path, "Port 22\nPermitRootLogin no\n")
        assert parser.errors == []

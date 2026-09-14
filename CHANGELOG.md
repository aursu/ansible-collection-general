# Changelog

All notable changes to `aursu.general` are documented here.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-09-14

Two new modules, and the module_utils behind one of them. No existing behaviour
changes, so 1.5.0 is a drop-in replacement for 1.4.0.

### Added

- **`aursu.general.sshd_info`** - parses an OpenSSH server configuration
  recursively, following `Include` directives, and returns the effective value of
  each option.

  It implements the **first match wins** rule that sshd actually applies, which
  is the opposite of the intuition most people bring to a config directory: a
  drop-in read early, such as one in `sshd_config.d/`, silently defeats the same
  option set later in the main file. The return therefore carries not just
  `value` but `location` - the file that won - and `appearance`, every file that
  set it. That distinction is the whole point: knowing an option is set somewhere
  is not the same as knowing which setting is in force.

- **`aursu.general.ssh_parser` module_utils** - `SshConfigParser` and
  `OptionStore`, which do the work above: recursive include resolution, match
  block handling, and re-parse logic. Unit tested.

- **`aursu.general.fstab_info`** - returns the **static** mount table from
  `/etc/fstab`, read with `findmnt --fstab -J`. Optional `path` narrows the
  result to a single mount point.

  This fills a gap `dev_info` cannot. `dev_info` runs `findmnt -J`, which reports
  the **live** table: the device as actually mounted and the kernel's effective
  options. `nofail` and `_netdev` are directives to the systemd fstab generator
  rather than kernel mount options, so they never appear there. Any check for
  them against live output fails on every run and can never converge.

  The two views also disagree about the source once fstab goes stale, and that
  disagreement is a boot hazard rather than a curiosity: an entry whose device no
  longer exists fails `local-fs.target` at the next boot, and without `nofail`
  the host never reaches `multi-user.target` - it answers ICMP while refusing
  every TCP port, which on a machine without console access is unrecoverable.

  Lookup is by mount point rather than by device deliberately. A stale source
  cannot be resolved back to a device, so a device-keyed lookup returns nothing
  for precisely the entries that are broken. Unit tested in
  `tests/unit/plugins/modules/test_fstab_info.py`.

- **CI** - `test.yml` runs the unit suite on push and pull request; `release.yml`
  builds and publishes to Ansible Galaxy on a `v*` tag, refusing to publish when
  the tag does not match the version in `galaxy.yml`.

- `.gitignore` and a `docker-compose.yml` for running the unit tests locally.

### Fixed

- `lvm_info`'s `DOCUMENTATION` could not be parsed by `ansible-doc` at all. Two entries in the
  `unit` description contained a bare `": "` inside a plain YAML scalar - `Acceptable values: ...`
  and `For example, C(unit: G) ...` - so YAML read the first as a mapping and the renderer failed
  with `Expected string in description of unit at index 2`. Both are now quoted, with the wording
  unchanged.

- `fstab_info`'s own `DOCUMENTATION` had the identical fault on its second description entry, and
  the module would not render either. Found by the new documentation job before release rather
  than after it, which is the argument for having one.

- `sshd_info` declared `version_added: "1.0.0"`, copied from `lvm_info`. It is new in 1.5.0.

## [1.4.0]

Baseline for this changelog; earlier releases are recorded in the git history
only.

[1.5.0]: https://github.com/aursu/ansible-collection-general/releases/tag/v1.5.0

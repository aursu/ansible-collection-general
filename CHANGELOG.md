# Changelog

All notable changes to `aursu.general` are documented here.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-09-14

### Added

- **`aursu.general.fstab_info`** - returns the **static** mount table from
  `/etc/fstab`, read with `findmnt --fstab -J`. Optional `path` narrows the
  result to a single mount point. Unit tested in
  `tests/unit/plugins/modules/test_fstab_info.py`.

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
  for precisely the entries that are broken.

- **CI.** `test.yml` runs the unit suite and `ansible-doc` on push and pull
  request. `release.yml` builds and publishes to Ansible Galaxy on a `v*` tag,
  refusing to publish when the tag does not match `galaxy.yml`, or when that
  version is **already published on Galaxy** - see below for why that second
  check exists.

### Fixed

- `lvm_info`'s `DOCUMENTATION` could not be parsed by `ansible-doc` at all. Two
  entries in the `unit` description contained a bare `": "` inside a plain YAML
  scalar - `Acceptable values: ...` and `For example, C(unit: G) ...` - so YAML
  read the first as a mapping and the renderer failed with
  `Expected string in description of unit at index 2`. Both are now quoted, with
  the wording unchanged. It had been in that state since it was written.

- `fstab_info`'s own `DOCUMENTATION` had the identical fault and would not render
  either. Caught by the new documentation job before release rather than after,
  which is the argument for having one.

- `sshd_info` declared `version_added: "1.0.0"`, copied from `lvm_info`. It was
  released in 1.5.0 and now says so.

- **`galaxy.yml` said `1.4.0` while Galaxy had already served `1.5.0` since
  2026-02-04.** The 1.5.0 release was published from a working tree whose version
  bump was never committed, so the repository understated the released version by
  a whole release for seven months. Two things now guard against a repeat: the
  version lives in a tagged commit, and `release.yml` refuses to publish a
  version Galaxy already holds - Galaxy does not allow re-uploading a version, so
  discovering this at publish time means an unusable tag rather than a warning.

## [1.5.0] - 2026-02-04

Published to Galaxy on 2026-02-04. Recorded here retrospectively: the release was
made without a git tag, and without the `galaxy.yml` bump being committed.

### Added

- **`aursu.general.sshd_info`** - parses an OpenSSH server configuration
  recursively, following `Include` directives, and returns the effective value of
  each option.

  It implements the **first match wins** rule that sshd actually applies, which
  is the opposite of the intuition most people bring to a config directory: a
  drop-in read early, such as one in `sshd_config.d/`, silently defeats the same
  option set later in the main file. The return therefore carries not just
  `value` but `location` - the file that won - and `appearance`, every file that
  set it. That distinction is the point: knowing an option is set somewhere is
  not the same as knowing which setting is in force.

- **`aursu.general.ssh_parser` module_utils** - `SshConfigParser` and
  `OptionStore`, which do the work above: recursive include resolution, match
  block handling, and re-parse logic. Unit tested.

- `.gitignore`, and a `docker-compose.yml` for running the unit tests locally.

## [1.4.0] - 2025-05-16

Baseline for this changelog; this and earlier releases are recorded in the git
history and on Galaxy only.

[1.6.0]: https://github.com/aursu/ansible-collection-general/releases/tag/v1.6.0
[1.5.0]: https://galaxy.ansible.com/ui/repo/published/aursu/general/

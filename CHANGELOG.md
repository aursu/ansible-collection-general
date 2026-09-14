# Changelog

All notable changes to `aursu.general` are documented here.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-09-14

### Added

- `aursu.general.fstab_info` — returns the **static** mount table from `/etc/fstab`, read with
  `findmnt --fstab -J`. Optional `path` narrows the result to a single mount point.

  This fills a gap that `dev_info` cannot: `dev_info` runs `findmnt -J`, which reports the **live**
  mount table — the device as actually mounted and the kernel's effective options. `nofail` and
  `_netdev` are directives to systemd's fstab generator rather than kernel mount options, so they
  never appear there. Any check for them against live options fails on every run and can never
  converge.

  The two views also disagree about the source when fstab has gone stale, and that disagreement is
  a boot hazard rather than a curiosity: an fstab entry whose device no longer exists fails
  `local-fs.target` at the next boot, and without `nofail` the host does not reach
  `multi-user.target`.

  Lookup is by mount point rather than by device deliberately. A stale source cannot be resolved
  back to a device, so a device-keyed lookup returns nothing for precisely the entries that are
  broken.

### Notes

- No existing behaviour changes. `dev_info` and `lvm_info` are untouched, so 1.5.0 is a drop-in
  replacement for 1.4.0.

## [1.4.0]

Baseline for this changelog; earlier releases are recorded in the git history only.

[1.5.0]: https://github.com/aursu/ansible-collection-general/releases/tag/v1.5.0

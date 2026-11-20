# 01 — Kernel inventory and `kernel_info`

| | |
|---|---|
| Release | 1.8.0 (2026-11-20) |
| PR | #1 `feature/kernel-info`, merged as `188afaa` |
| Commits | `88c60ad` module_utils/kernels, `77dccc6` kernel_info module |

## What

A read-only inventory of the kernels installed on a host: every package that
belongs to each kernel, its bootable release, whether it is running, whether it
is the newest, and how much of `/boot` it occupies. Exposed as the module
`aursu.general.kernel_info`; the code behind it is shared through
`plugins/module_utils/kernels.py`.

## Why — the goal

A host's 442 MB `/boot` filled up with four kernels of ~105 MB each, and a
package install then failed rebuilding the initramfs ("No space left on
device"). Old kernels must be removed by a **policy**, not by a hand-written list
of packages. A policy needs facts first: which kernels exist and which packages
make up each. This change is that fact layer; the removal lives elsewhere
(`aursu.baseprofile.kernel_cleanup`), because this collection only reads
(`docs/design/collection-boundaries.md`).

## How it works

1. **Query.** `dpkg-query -W -f '${Package}\t${db:Status-Abbrev}\n' 'linux-*'`.
   Exit 0 when something matches; exit 1 with empty output when nothing matches
   (measured on Ubuntu 24.04) — an empty inventory, not an error. Any other exit
   fails the module.
2. **Filter by state.** The second letter of the status abbreviation is the
   current state. `n` (not installed) and `c` (configuration files only) are
   skipped; everything else has files on disk and counts — including a
   half-configured `iF`, which still occupies `/boot`.
3. **Group by ABI version.** A per-kernel package ends in the kernel's ABI
   version, optionally followed by a flavour:
   `^(?P<prefix>linux-.+?)-(?P<version>\d+\.\d+\.\d+-\d+)(?:-(?P<flavour>[a-z][a-z0-9]*))?$`.
   Packages are grouped by `version`. Meta packages
   (`linux-generic-hwe-24.04`, `linux-headers-3.0`) do not match: their trailing
   number is not `x.y.z-n`.
4. **Releases.** A `linux-image-*` or `linux-image-unsigned-*` package with a
   flavour makes the version bootable; `<version>-<flavour>` is what `uname -r`
   reports. A version with only headers or tools left has no release.
5. **Order.** Numeric on the ABI version (`6.17.0-9` before `6.17.0-14`).
6. **Running / latest / size.** Running: `os.uname()[2]` is one of the
   version's releases. Latest: the newest version that has a release.
   `boot_bytes`: sum of `vmlinuz-`, `initrd.img-`, `System.map-`, `config-` for
   each release in the boot directory.

## Where it is defined

| File | What |
|---|---|
| `plugins/module_utils/kernels.py` | `DEBIAN_KERNEL_PACKAGE` (the grouping regex), `DEBIAN_IMAGE_PREFIXES`, `BOOT_FILES`; class `Kernel` (one version: packages, releases, `sort_key`, `has_image`, `boot_bytes()`); class `DebianKernelInventory` (`parse()` pure, `query()` runs dpkg-query, `collect()` returns the list of dicts) |
| `plugins/modules/kernel_info.py` | thin module: `installed_kernels`, `running_release`; option `boot_dir` |
| `tests/unit/plugins/module_utils/test_kernels.py` | 14 tests on a real fixture |
| `tests/unit/plugins/module_utils/fixtures/dpkg_query_ubuntu2404_hwe.txt` | real `dpkg-query` output: 4 kernels, 2 series, 14 `un`, 1 `rc` |
| `tests/unit/plugins/modules/test_kernel_info.py` | 3 tests of the module contract |
| `.github/workflows/test.yml` | `kernel_info` added to the `ansible-doc` check |

## Rejected alternatives

- **A list of known package prefixes** (`linux-image-`, `linux-modules-`,
  `linux-modules-extra-`, `linux-headers-`…). Measured on the real host: the 7.0
  series adds `linux-main-modules-zfs-*` and `linux-main-modules-v4l2loopback-*`
  and drops `linux-modules-extra-*`. A prefix list written for 6.17 misses
  packages on the next series.
- **Ordering by install date or by dpkg version strings.** The ABI version is in
  every package name and orders numerically without calling dpkg.
- **The removing module taking `kernel_info`'s output through the play.** The
  boundaries document forbids it: a module that changes state reads the state
  itself at the moment it acts. Hence the shared `module_utils`.

## Verified by

91 unit tests; `ansible-doc` of all modules; a live read-only run against an
Ubuntu 24.04 host: 4 kernels, 102–105 MB each in `/boot`, 7.0.0-43 running and
latest. Two of my own assumptions were wrong and caught before the commit: the
`dpkg-query` exit-code comment (fixed after measuring) and the expected package
count in one test (29, not 30).

## Not covered

RPM-based systems; the module fails cleanly without `dpkg-query`.

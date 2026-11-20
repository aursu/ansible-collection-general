# 03 — `validate_mount_point`

| | |
|---|---|
| Release | 1.10.0 (2026-11-20) |
| PR | `feature/mount-point-filter` |

## What

A filter that requires a directory to be a mount point of its own:
`ansible_facts.mounts | aursu.general.validate_mount_point('/var/lib/docker')`.
It returns `true`, or fails naming the mount that actually holds the path and its
device. The logic is the class `MountTable` in `plugins/plugin_utils/mounts.py`.

## Why — the goal

`home-manage`'s `playbook_docker.yml` must refuse to install Docker unless
`/var/lib/docker` is the dedicated LV — otherwise Docker would fill the 48 GB
root filesystem. The first version was a Jinja chain,
`ansible_facts.mounts | selectattr('mount', 'equalto', '/var/lib/docker') | list | length == 1`;
Alexander's rule is that such checks are Python filters. The chain also said
nothing useful when it failed.

## How it works

1. `MountTable(mounts)` keeps the entries of `ansible_facts.mounts` that have a
   string `mount`.
2. `holding(path)`: normalises the path; among the entries whose mount point is
   the path, `/`, or a prefix **by component** (`point + '/'`), picks the longest;
   on a tie the later entry wins (a mount over a mount shadows the earlier one).
3. `is_mount_point(path)`: the holder's mount point equals the path.
4. `validate_mount_point`: `true`, or `"<path> is not a mount point: it is on
   <mount> (<device>)."`, or "no mount in the table holds it" for an empty table.

## Where it is defined

| File | What |
|---|---|
| `plugins/plugin_utils/mounts.py` | `MountTable` (`holding`, `is_mount_point`) |
| `plugins/filter/mounts.py` | `validate_mount_point` and its documentation |
| `tests/unit/plugins/filter/test_mounts.py` | 10 tests |

## Rejected alternatives

- **The Jinja chain.** Rule: checks are Python filters; it also cannot say which
  mount holds the path.
- **A local filter in `home-manage`.** A mount-point check is general; other
  plays (storage, later data directories) need the same.
- **`path.startswith(point)`.** `/var/lib/docker2` would count as under
  `/var/lib/docker`; prefixes are compared by component.

## Verified by

122 unit tests (10 new). Against the facts of media-gw: `/var/lib/docker`
passes; `/srv` fails with `/srv is not a mount point: it is on / (/dev/nvme0n1p3).`

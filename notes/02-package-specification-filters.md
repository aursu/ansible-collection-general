# 02 — Package-specification filters

| | |
|---|---|
| Release | 1.9.0 (2026-11-20) |
| PR | #2 `feature/package-filters` |
| Commits | `1d8616f` |

## What

Two filters, `validate_package_names` and `validate_package_pins`, and the
classes behind them, `PackageNames` and `PackagePins`. They decide what a valid
package specification is. Each returns `true` or fails the task with a message
naming the variable and the offending entry.

## Why — the goal

Two collections validated package specifications on their own:

- `aursu.dockerinstall` used a Jinja chain,
  `docker_packages.values() | select('string') | select | list | length == docker_packages | length`.
  It was hard to read, impossible to unit-test, and on failure could not say
  **which** package was wrong.
- `aursu.lvm_setup` kept a private copy of the name rule in
  `RequiredPackages._package_list`.

Alexander's rule: a check like this is a Python filter, and when the same logic
appears in more than one collection it moves to `aursu.general` and is used from
there. One rule, one place, tested once.

## How it works

- `PackageNames(value, name)`: a string is wrapped in a list; the result must be
  a list whose every element is a non-empty string (whitespace-only counts as
  empty). An empty list is valid — nothing to install. Stores `names` as a tuple.
- `PackagePins(pins, name)`: must be a non-empty dict; every key a non-empty
  string; every value a non-empty string. A number gets the hint
  "Quote it in YAML", because that is how an unquoted version arrives — `0.39`
  stays a float, `1.10` becomes `1.1`. `null` (a key with no value) is refused the
  same way. Stores a copy as `pins`.
- The filters construct the class and return `true`; the class raises
  `AnsibleFilterError`, which fails the task. The optional `name` argument is the
  variable name used in the message, e.g.
  `'docker_packages['docker-buildx-plugin']' must be an exact version string, got 0.39. Quote it in YAML.`

## Where it is defined

| File | What |
|---|---|
| `plugins/plugin_utils/packages.py` | `PackageNames`, `PackagePins` — the rules; importable by other collections' controller-side plugins |
| `plugins/filter/packages.py` | the two filters and their documentation |
| `tests/unit/plugins/filter/test_packages.py` | 21 tests: valid input, every malformed form, the messages |

## Rejected alternatives

- **A per-item `assert` loop in the role** (`loop: docker_packages | dict2items`).
  Readable and names the package, but the rule would still live in every role
  that pins packages. Alexander chose the shared filter.
- **Role argument specs** (`meta/argument_specs.yml`). They check that a variable
  is a dict, but cannot express "every value of an arbitrary-key dict is a
  non-empty string".
- **Putting the classes in `module_utils`.** Filters run on the controller;
  `plugin_utils` is the place for controller-side shared code, and it does not
  get shipped to hosts with modules.

## Placement

`aursu.general` is the read-only layer. A filter that only checks its input and
changes nothing fits it; `plugins/filter/utils.py` already holds general
filters there.

## Consumers

- `aursu.dockerinstall` 1.0.0 (`roles/docker/tasks/main.yml`):
  `validate_package_pins` for `docker_packages`, `validate_package_names` for
  `docker_prerequisite_packages`.
- `aursu.lvm_setup` 1.6.0 (`plugins/plugin_utils/package_helpers.py`):
  `RequiredPackages` uses `PackageNames` instead of its private copy.

## Verified by

112 unit tests (21 new); the filters run by FQCN in a real playbook (a valid map
passes, `0.39` fails with the message above); `ansible-doc -t filter` renders;
`release_preflight.py --tag v1.9.0` passes.

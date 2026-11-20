# Development notes — aursu.general

One note per change: what it is, why it was made, how it works, where each part
is defined, and the alternatives that lost. Numbered in the order the changes
landed. Notes start with 1.8.0; earlier history is in `CHANGELOG.md`.

| # | Release | Subject |
|---|---|---|
| [01](01-kernel-inventory.md) | 1.8.0 | Kernel inventory (`module_utils/kernels.py`) and `kernel_info` |
| [02](02-package-specification-filters.md) | 1.9.0 | `validate_package_names`, `validate_package_pins` (`plugin_utils/packages.py`) |

Not part of the published collection (`build_ignore`).

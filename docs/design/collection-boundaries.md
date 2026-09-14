# Where the code lives

## Two collections, split by what they do to the host

**`aursu.general`** is the facts layer. Every module in it is read-only: `dev_info`,
`lvm_info`, `fstab_info`, `sshd_info`. It is safe to run anywhere, at any time, on any
schedule - compliance checks, inventory, monitoring. Nothing in it changes a host.

**`aursu.ssh_setup`** is the layer with teeth. It changes state: inserting, removing and
cleaning up SSH configuration, and in time SFTP setup, client configuration and key material.

The naming convention follows from this. `aursu.general` accumulates `*_info` modules; a
collection that modifies something gets its own namespace entry rather than being folded in
beside them.

Terminology, since it is easy to mix up:

- **module** - a Python file that does one job on a host (`sshd_info.py`, `config.py`)
- **collection** - the distributable package holding modules, plugins and roles
  (`aursu.general`)
- **role** - YAML that composes modules into a task (`configure secure SSH`)

## Sharing the parser without coupling the modules

Both layers need to understand an sshd configuration. The parser therefore lives in
`aursu.general/plugins/module_utils/ssh_parser.py`, and `aursu.ssh_setup` declares a dependency:

```yaml
# aursu.ssh_setup/galaxy.yml
dependencies:
  "aursu.general": ">=1.0.0"
```

```python
from ansible_collections.aursu.general.plugins.module_utils.ssh_parser import SshConfigParser
```

### What must not be done instead

**Do not feed `sshd_info`'s output into the writer through the playbook.** It is the obvious
shortcut and it is wrong:

```yaml
# DO NOT DO THIS
- aursu.general.sshd_info:
    register: sshd

- aursu.ssh_setup.config:
    parsed_config: "{{ sshd.sshd_config }}"    # stale by construction
```

Between those two tasks anything may have touched the file - a template, a hand edit, another
play. The writer would then be editing according to a map that no longer describes the disk. A
module that changes state must read the current state itself, at the moment it acts.

Sharing the *code* is DRY. Sharing the *output* is coupling.

### What was tried and abandoned

An intermediate proposal put only a helper in `module_utils` that returned the flat list of
configuration files reachable through `Include`, leaving each module to parse them itself. That
is the worst of both: the hard part - scope tracking, first-match-wins, merging Match blocks -
gets written twice, while the trivial part is shared.

The whole parser moves into `module_utils`. `sshd_info` becomes a thin wrapper that calls it
and returns the structure; the writer calls the same parser to find out which file holds the
effective value and which files hold duplicates.

## Documentation blocks in module_utils

Galaxy expects `DOCUMENTATION`, `EXAMPLES` and `RETURN` in `module_utils` files, not just in
modules. The convention differs slightly from a module's:

- `DOCUMENTATION` uses a `module_utils:` key instead of `module:`
- `EXAMPLES` holds **Python**, not YAML task snippets - it shows how to import and drive the
  classes
- `RETURN` documents what the file **exports** - the classes - not their methods. Listing a
  method such as `get_structured_data` at the top level of `RETURN` is a documentation error;
  describe it inside the class entry instead.

## Suppressing import errors from linters

`ansible.module_utils.basic` is not installed in a plain development virtualenv, so Pylint and
Pylance both complain. Put the suppressions at the top of the file rather than on every import
line:

```python
#!/usr/bin/python
# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pylint: disable=import-error
```

The better fix, where practical, is `pip install ansible-core` into the environment the editor
uses - that gives working navigation into `AnsibleModule` as well as silence.

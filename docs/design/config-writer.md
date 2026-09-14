# Specification: the writer module

Status: **built.** Lives in `aursu.ssh_setup/plugins/modules/config.py`, which depends on
`aursu.general >= 1.5.0` for the shared parser. This document records the design and the
behaviour the implementation is expected to keep.

## What it does

Sets or removes one SSH option, in the global scope or inside a named `Match` block, across the
main configuration file and everything it includes - while leaving comments, blank lines and
indentation exactly as they were.

```yaml
- name: Set the port globally
  aursu.ssh_setup.config:
    key: Port
    value: "2222"

- name: Disable password authentication for one user
  aursu.ssh_setup.config:
    key: PasswordAuthentication
    value: "no"
    condition: "User bob"

- name: Fall back to the sshd default
  aursu.ssh_setup.config:
    key: PermitRootLogin
    state: absent
```

| Parameter | Required | Default | Meaning |
|---|---|---|---|
| `key` | yes | - | Option name |
| `value` | for `present` | - | Value to set |
| `condition` | no | `global` | Match condition, or `global` |
| `config_path` | no | `/etc/ssh/sshd_config` | Main file |
| `state` | no | `present` | `present` or `absent` |
| `backup` | no | `false` | Back up before writing |

Use `state`, the Ansible standard. An earlier draft used a `mode="ensure_present"` /
`mode="ensure_absent"` flag - a custom vocabulary for a concept Ansible already names, and one
that turns a single function into two tangled ones.

## The algorithm

The whole design rests on the fact that the parser already answers the two questions that
matter. It reports `location` - the file holding the effective value - and `appearance` - every
file the directive occurs in. No second scan is needed.

**1. Analyse.** Run the shared parser over `config_path`. Extract `location` and `appearance`
for the requested key in the requested scope.

**2. Act.**

*`state: present`, option exists:*
- rewrite the value in `location`, preserving that line's indentation;
- remove the directive from every other file in `appearance` - those are shadowed duplicates,
  and leaving them makes the effective configuration ambiguous on the next edit.

*`state: present`, option does not exist:* insert it.

- **global scope:** before the **first** `Match` block in the main file, or at end of file if
  there is none. This placement is not cosmetic - anything written after a `Match` header falls
  inside that block.
- **inside a Match block that exists:** immediately after the block's header line, indented.
- **inside a Match block that does not exist:** append a new block at end of file.

*`state: absent`:* remove the directive from every file in `appearance`.

**3. Removal means commenting out**, not deleting:

```
# PermitRootLogin yes # Removed by Ansible
```

It leaves an audit trail, it is reversible by hand, and it cannot silently destroy a line
somebody cared about.

## Reading and writing

Read with `readlines()` into a list, edit elements of that list, write the whole list back.
This preserves everything the parser does not model - comments, blank lines, odd indentation,
trailing whitespace - because untouched lines are never reconstructed, only copied.

Write atomically: `tempfile.mkstemp` in the destination directory, then `module.atomic_move`.

## Implementation: smart lines

Two shapes were considered for the editing pass.

**Strategy / callback.** One engine walks the file and tracks scope; a callback decides what to
do with a matching line. Removes the `mode` flag cleanly and isolates each action.

**Smart lines - chosen.** Each raw line becomes an object that knows what it is. The parsing
mess moves into the classes, and the main loop reads like prose.

```python
class SshLine:          # base; holds raw text, modified flag, diff entry
class IgnoredLine       # comments, blanks, Include, unparseable lines
class MatchLine         # carries .scope
class ConfigLine        # carries .key, .key_lower, .value, .indent
```

Construction goes through a factory method on the base class, so callers never touch `shlex`:

```python
line_objects = [SshLine.create(line) for line in raw_lines]
```

The loop then contains no lexing, no indentation arithmetic and no `startswith('#')`:

```python
for obj in line_objects:
    if isinstance(obj, MatchLine):
        current_scope = obj.scope
        continue
    if isinstance(obj, ConfigLine):
        if current_scope == target_scope and obj.key_lower == target_key_lower:
            obj.comment_out() if state == "absent" else obj.update(target_value)
```

`ConfigLine.update()` regenerates its own text from `indent`, `key` and the new value, so the
original indentation and the file's own capitalisation of the key survive. It returns `False`
and sets nothing when the value already matches - that is where idempotence comes from.

### Constructors take optional pre-split tokens

The factory has already run `shlex.split` to decide which class to build. Passing the result to
the constructor avoids splitting twice:

```python
def __init__(self, raw_content, parts=None):
    if parts is None:
        parts = shlex.split(raw_content.strip())   # standalone use, e.g. in tests
```

This keeps the object valid however it is created. The alternative - an empty constructor plus
a `from_parts` classmethod - allows a half-initialised object to exist, which is worse than the
duplicated split it avoids.

### An unparseable line becomes IgnoredLine

If `shlex` raises on unbalanced quotes, the factory returns `IgnoredLine` and the line is
copied through untouched. A writer must never destroy a line it failed to understand.


## Two designs that were considered and not taken

Recorded because both are reasonable, and whoever revisits this will think of them again.

**Reader-state plus actions.** Pull scope tracking into a `ContextTracker` helper that is fed
one line at a time and answers "does this line match the target scope and key?". Then expose
two plain public methods, `ensure_key_present` and `ensure_key_absent`, both delegating to a
private rewrite loop that takes a per-line callback. Less invasive than smart lines - no class
hierarchy - but the line still has to be re-parsed wherever it is acted on.

**Strategy / callback injection.** One engine walks the file and tracks scope; a closure decides
what to do with a matching line and returns `(new_line, modified, diff)`. This removes the
`mode` flag as cleanly as smart lines do, and isolates "how to comment a line out" in one small
function. It was passed over only because smart lines put the parsing in one place as well,
which the callback version does not.

If the smart-line hierarchy ever starts to feel heavy for what it does, the strategy version is
the fallback - and the behavioural contract above is what proves the swap was safe.

## An optional convenience

`process_file(..., state="present")` is fine, and `state` is the Ansible-standard spelling. If
call sites start to read poorly, two thin wrappers remove the keyword without reintroducing a
custom vocabulary:

```python
def ensure_present(self, filepath, scope, key, value):
    return self.process_file(filepath, scope, key, target_value=value, state="present")

def ensure_absent(self, filepath, scope, key):
    return self.process_file(filepath, scope, key, state="absent")
```

Deferred rather than rejected - `state="present"` is already the idiom Ansible users expect.

## Behaviour to hold under refactoring

Any reimplementation has to keep these true. They are the module's contract.

1. Value already correct - nothing written, `changed: false`, no temp file, no move.
2. Value differs - rewritten in `location`, indentation preserved, all other lines intact.
3. `state: absent` - the line is commented with the removal marker, not deleted.
4. New global option - inserted **before** the first `Match` block.
5. New option in an existing block - inserted after that block's header, indented.
6. New option in a block that does not exist - new block appended at end of file.
7. Option present in main file and an include - main file updated, include cleaned, **two**
   files written.

## Verified behaviour

All of the above was exercised against real files on 2026-09-15, driving the module through
`ansible localhost -c local -m aursu.ssh_setup.config` over a fixture with a main file, an
include, and a `Match User bob` block. Thirteen checks, all passing:

| Contract point | Checked |
|---|---|
| 1. already correct | second identical run reports `changed: false`, nothing written |
| 2. value differs | rewritten in place; comments and other options untouched |
| 3. `state: absent` | line commented with the removal marker, not deleted |
| 4. new global option | inserted before the first `Match`, not into it |
| 5. update inside a block | value changed, indentation preserved |
| 6. insert into a block | placed after the header line, indented |
| 7. new block | appended at end of file |
| 8. shadowed duplicate | winner updated in `location`, duplicate commented in the include |

### `changed` counts cleanup, and convergence can take two runs

Worth knowing before writing an idempotence test. Setting an option to the value it already
holds still reports `changed: true` **if a shadowed duplicate had to be removed elsewhere** -
because removing it is real work, and the effective configuration was ambiguous until it was
done.

```
run 1:  Port=22, main already says 22, include says 2222
        -> changed: true   (include's "Port 2222" commented out)

run 2:  identical invocation
        -> changed: false  (nothing left to clean)
```

This is correct, not a defect. A test that asserts `changed: false` on the first run of a
fixture containing duplicates is asserting the wrong thing.

## What the collection still lacks

There is no `tests/` directory, although `galaxy.yml` lists `tests/unit/` under `build_ignore`.
The behaviour above is verified by hand and nothing guards it against regression - which
matters precisely because the smart-line design is meant to be swappable for the strategy
version.

The test approach is described in
[../development/unit-testing.md](../development/unit-testing.md); a writer needs the extra layer
covered there, intercepting `tempfile.mkstemp` and `os.fdopen` to capture what would be written
before `atomic_move` is called, and inspecting the calls to `atomic_move` to confirm which files
were touched.

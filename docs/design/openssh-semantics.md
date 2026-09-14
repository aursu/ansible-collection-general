# What sshd actually does

Everything here is about the daemon's behaviour, not the parser's. The parser exists to model
it, so where the two differ it is recorded as a deliberate difference rather than a bug.

## First match wins

For most directives sshd takes the **first** value it encounters and ignores every later one.
This is the opposite of the intuition people bring from configuration directories, where a
higher-numbered drop-in is usually expected to override.

The practical consequence, and the reason this tooling exists:

```
# /etc/ssh/sshd_config
Include /etc/ssh/sshd_config.d/*.conf
PasswordAuthentication yes          <- does nothing
```

```
# /etc/ssh/sshd_config.d/50-cloud-init.conf
PasswordAuthentication no           <- this is in force
```

Because the `Include` is read before the setting below it, a drop-in silently defeats the main
file. Knowing an option is set somewhere is not the same as knowing which setting is in force,
which is why the model reports `location` alongside `value`.

## Match blocks

### The same condition may appear many times

`Match User deploy` can occur in the main file and again in an included file - or twice in the
same file, which is bad practice but valid. sshd reads the configuration as one stream, so each
occurrence simply adds options to that condition's context.

Within a condition, conflicts resolve the same way as globally: first occurrence wins, later
ones are shadowed.

The parser therefore **merges** blocks with the same condition into a single entry. The block's
own `location` is the first file that declared it; `appearance` lists all of them.

### `Match All` resets to global

`Match All` is the idiom for leaving a Match context and returning to settings that always
apply. The parser treats it as a switch back to the global scope rather than as a block
named "All".

## Include

`Include` behaves as a textual insertion at the point it appears. Files matched by a glob are
processed in **lexical order**, which is why the implementation sorts them - without sorting,
the effective configuration would depend on directory order.

A relative `Include` path resolves against `/etc/ssh`, not against the directory of the file
containing the directive.

### The file isolation rule

This is the part that is easy to get wrong, and it was got wrong once during design before
being corrected.

**End of file ends any Match block opened inside that file.** Scope does not leak back to the
parent.

```
# /etc/ssh/sshd_config
Match User deploy
    Include /etc/ssh/weird.conf
    Banner /etc/issue        <- still inside "Match User deploy"
```

```
# /etc/ssh/weird.conf
Match Address 10.0.0.1
    AllowTcpForwarding yes
# EOF - the Address block closes here
```

`Banner` belongs to `User deploy`. The incorrect model - that the included file's trailing
`Match` stays active after the return, capturing `Banner` into `Address 10.0.0.1` - would
change which host gets the banner, so the distinction is not academic.

It works as a stack: the parent's context is saved on entry to the include and restored on
return.

The implementation gets this for free. The active scope is a **local variable** inside the
recursive parse function rather than an attribute on the parser object. When the function
returns, the caller's own variable is simply still in scope. An earlier version stored it as
`self.parent_scope` and broke on nested includes, because the second include overwrote the
first one's saved value.

### Include inside a Match block

Permitted, and the included file's options join the enclosing Match context. The options'
`location` points at the included file while they live logically inside the block - that is
correct and expected.

## Cumulative directives

Some directives are not shadowed at all: every occurrence takes effect.

This list is **measured, not taken from the manual page** - each entry was verified against
OpenSSH 9.9p1 by writing a configuration with two occurrences and reading back `sshd -T`.

| Cumulative - all occurrences apply | Shadowed - first wins |
|---|---|
| `Port` | `SetEnv` |
| `ListenAddress` | `PermitOpen` |
| `HostKey` | `PermitListen` |
| `AcceptEnv` | `PermitRootLogin` |
| `AllowUsers`, `DenyUsers` | `PasswordAuthentication` |
| `AllowGroups`, `DenyGroups` | `MaxAuthTries` |
| `Subsystem` (distinct names) | `AuthorizedKeysFile`, `LogLevel` |

The right-hand column is the reason for measuring. `SetEnv`, `PermitOpen` and `PermitListen`
all look like they should accumulate and do not.

## Accepted syntax

sshd accepts three spellings of the same directive, all verified against 9.9p1:

```
MaxAuthTries 5
MaxAuthTries=5
MaxAuthTries = 5
```

A parser that handles only whitespace separation will read `PermitRootLogin=prohibit-password`
as a directive *named* `PermitRootLogin=prohibit-password` with an empty value - and then
report `PermitRootLogin` as absent, which for an audit is the worst available failure
direction.

Comments are only recognised at the start of a line. A `#` mid-line is part of the value.

## Where the parser deliberately differs from sshd

### Include loops

Real sshd has **no loop detection**. It has a nesting depth limit, around 16, and on exceeding
it refuses to start:

```
/etc/ssh/sshd_config line 1: Include nested too deeply
```

So `A includes B includes A` is a fatal configuration error - the daemon is down.

The parser instead tracks the files in the current call stack and declines to re-enter one,
then carries on and returns what it could read.

| | Parser | sshd |
|---|---|---|
| Logic | have I already entered this file in this chain? | keep descending until depth > 16 |
| On `A -> B -> A` | reads both, skips the re-entry, returns data | fatal, refuses to start |
| Goal | survive and report | do not hang or overflow the stack |

This is the right behaviour for an information module: a broken configuration should not crash
the playbook. But it means the module can return a clean-looking answer for a host whose sshd
is dead. If loop protection triggers, say so in the output rather than silently.

### Loop protection must use the call stack, not a global set

An early implementation kept a `processed_files` set and skipped any file it had already seen.
That breaks a legitimate pattern:

```
Match User admin
    Include /etc/ssh/common_security.conf
Match User deploy
    Include /etc/ssh/common_security.conf     <- silently skipped
```

The same file included in two different contexts must be parsed twice, once per context.
Only re-entry **within the current chain** is a loop. The stack is copied on each descent so
that sibling branches do not see each other's entries.

### Written, not computed

The parser reports the configuration **as written**. `sshd -T` reports what the daemon computed
from it. Two differences to expect:

- sshd canonicalises deprecated aliases - `prohibit-password` is reported by the parser,
  `without-password` by `sshd -T`;
- sshd expands `ListenAddress` against every `Port` into concrete listeners
  (`127.0.0.1:22`, `127.0.0.1:2222`, ...); the parser returns the addresses as configured.

Neither is a defect. A tool that edits files has to speak in terms of what is in the files.

# The data model

## Config-oriented, not directive-oriented

An earlier draft organised the output around each directive, carrying `scope` on the option and
listing its variants:

```yaml
# REJECTED
PasswordAuthentication:
  name: "PasswordAuthentication"
  value: "no"
  scope: "global"
  location: "/etc/ssh/sshd_config"
  matches:
    - value: "yes"
      condition: "User anoncvs"
```

That is an index of directives. What is wanted is a picture of the **configuration**: what is
written where. So the structure follows the file's own shape - global options at the root, and
`Match` blocks as a separate collection hanging off it.

```yaml
# Root = global scope
Port:
  value: "22"
  location: /etc/ssh/sshd_config
  appearance:
    - /etc/ssh/sshd_config
    - /etc/ssh/sshd_config.d/old.conf

PasswordAuthentication:
  value: "no"
  location: /etc/ssh/sshd_config.d/50-cloud-init.conf
  appearance:
    - /etc/ssh/sshd_config.d/50-cloud-init.conf
    - /etc/ssh/sshd_config

Match:
  - condition: "User anoncvs"
    location: /etc/ssh/sshd_config
    appearance:
      - /etc/ssh/sshd_config
      - /etc/ssh/sshd_config.d/custom.conf
    options:
      Banner:
        value: /etc/banners/anon
        location: /etc/ssh/sshd_config
        appearance: [/etc/ssh/sshd_config]
```

## Three fields, and what each is for

**`value`** - the setting actually in force. For a shadowed directive this is the first
occurrence, because that is the one sshd uses.

**`location`** - the file the winning value came from. This is the file to **edit**.

**`appearance`** - every file the directive occurs in, de-duplicated, in encounter order. This
is the **cleanup list**. It is not decoration and not diagnostics: it exists so that a writer
can act on it directly.

> To change a setting: edit `location`, delete the directive from every other file in
> `appearance`. To remove it entirely: delete it from every file in `appearance`.

That single sentence is the reason both fields exist. Any change to the model has to keep it
true.

## Match blocks are a list, not a map

Two candidates were considered. A map keyed by condition string reads well for an auditor, and
groups `Match User bob` from three files into one entry automatically. A list of objects, each
carrying its own `condition`, is what the model uses.

The reason is uniformity: `Match` is the only key at the root that is not an SSH option, and
making it a list keeps every other root key an option name. A map would put condition strings
into the same namespace as directives.

Blocks with the same condition are still merged into one list entry regardless of how many
files they are spread across - see [openssh-semantics.md](openssh-semantics.md).

## Options are nested under `options`, not flattened

Inside a `Match` entry the settings live under an `options` key rather than beside `condition`
and `location`. This was a deliberate change from an earlier flat shape.

Two reasons. Iteration is clean - you loop over `block.options` without filtering out
metadata keys. And there is no namespace collision: an SSH directive named `Location` would
otherwise land next to the block's own `location` metadata and one would silently overwrite the
other.

## Deliberately left out

Three things were proposed during design and rejected. They keep getting re-proposed because
each sounds useful in isolation, so the reasoning is recorded here.

### Line numbers

Rejected. `location` names a file, not a file and a line.

The argument for them was precision: knowing exactly which line to rewrite. The argument
against won on two counts. Configuration files for sshd are small and are read line by line
anyway, so a writer can simply find the directive again while it streams the file - there is
nothing to index. And carrying line numbers means every edit invalidates the numbers after it,
which forces either reverse-order application or re-parsing. That is real complexity bought for
no gain.

### Value history

Rejected, in those words: *this is already overkill.*

The proposal was a `values_list` (or `shadowed_value`) recording every value a directive was
given, so an audit could show "this was set three times with two different values". The model
carries only the effective value.

`appearance` already answers the operationally useful question - *which files do I have to
touch* - without carrying the values themselves.

### A `name` field on each option

Dropped from the output. The parser keeps the original spelling internally, because option
lookup is case-insensitive while the file's own capitalisation should be preserved when
rewriting a line. But the exported key **is** the name, so repeating it inside the object is
redundant.

## Cumulative directives

Some directives are not shadowed. Every occurrence of `Port`, `ListenAddress`, `HostKey`,
`AcceptEnv`, `AllowUsers`, `DenyUsers`, `AllowGroups`, `DenyGroups` and `Subsystem` takes
effect - see [openssh-semantics.md](openssh-semantics.md), where the list is measured rather
than assumed.

For those, reporting a single `value` is not a summary, it is wrong: a host with two
`ListenAddress` lines has two listening addresses.

**Resolved in 1.7.0: `value` carries the list.**

```yaml
ListenAddress:
  value: ["10.0.0.1", "10.0.0.2"]   # all of them, all in force
  cumulative: true
  location: /etc/ssh/sshd_config
  appearance: [/etc/ssh/sshd_config]
```

There is one field for the setting either way - a string when the directive is shadowed, a list
when it is cumulative - and the `cumulative` flag, present only on the latter, says which to
expect. A second field holding "the other values" was rejected: two fields for one setting is
ambiguous, and the reader has to work out which one is authoritative.

The type follows the flag and **not the count**. A cumulative directive written once still
yields a one-item list, so a caller never has to handle both shapes for the same directive.

This is not value history returning by another route. The distinction is whether the extra
values are *in force*: for a shadowed directive the later ones do nothing and are not recorded,
and `appearance` remains the only trace of where they were written.

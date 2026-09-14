# Design notes

These documents record the reasoning behind the OpenSSH configuration tooling in this
collection: what the data model is, why it has that shape, which alternatives were rejected
and why, and what OpenSSH actually does as opposed to what it appears to do.

They exist because most of this was settled in a long design conversation and would otherwise
survive only as folklore. Several of the decisions look arbitrary until you know the
alternative that was tried first.

| Document | What it settles |
|---|---|
| [design/data-model.md](design/data-model.md) | The shape of the parsed configuration, and the three things deliberately left out of it |
| [design/openssh-semantics.md](design/openssh-semantics.md) | How sshd really resolves options: first match wins, Include scoping, cumulative directives |
| [design/collection-boundaries.md](design/collection-boundaries.md) | Why reading and writing live in separate collections, and how they share code without coupling |
| [design/config-writer.md](design/config-writer.md) | Specification for the writer module, which does not exist yet |
| [development/unit-testing.md](development/unit-testing.md) | How to test a parser that touches the filesystem, and the four mocks people forget |
| [development/publishing.md](development/publishing.md) | Build and release mechanics |

## The one-paragraph summary

`sshd_info` reads an OpenSSH server configuration, follows every `Include`, and reports what
each option is set to **and where**. It is config-oriented rather than directive-oriented: the
root of the returned structure is the global scope, and `Match` blocks hang off it as a list.
For every option it reports `value` (the setting that is in force) and two pieces of location
data - `location`, the file that setting came from, and `appearance`, every file the directive
occurs in. Those two exist so that a separate writer module can edit the first and clean up
the rest.

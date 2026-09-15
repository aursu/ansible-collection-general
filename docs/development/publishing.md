# Build and release

## Compose services

Three services, one image, one mounted working directory:

```yaml
services:
  tests:
    working_dir: /var/ansible/project
    volumes:
      - ./:/var/ansible/project
    image: "ghcr.io/aursu/rockylinux:<tag>-ansible"
    command: pytest -v tests/unit

  build:
    working_dir: /var/ansible/project
    volumes:
      - ./:/var/ansible/project
    image: "ghcr.io/aursu/rockylinux:<tag>-ansible"
    command: ansible-galaxy collection build

  publish:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./:/var/ansible/project
    environment:
      - VERSION
    secrets:
      - galaxy_token

secrets:
  galaxy_token:
    file: ${HOME}/.ansible/galaxy_token
```

`--remove-orphans` can be made the default by putting `COMPOSE_REMOVE_ORPHANS=true` in `.env`
rather than remembering the flag.

## The token is a secret, not an environment variable

Passing the Galaxy token through `environment:` or on the command line exposes it in `ps` output
and in shell history. A top-level `secrets:` entry mounts it at `/run/secrets/galaxy_token`
inside the container, on tmpfs.

## No shell one-liners in YAML

An early version inlined the whole publish command:

```yaml
command: >
  sh -c 'ansible-galaxy collection publish "aursu-general-${VERSION}.tar.gz"
         --api-key "$$(cat /run/secrets/galaxy_token)"'
```

The `sh -c` is unavoidable there - `ansible-galaxy` is a binary and cannot expand `$(cat ...)`
or `${VERSION}` itself; only a shell can. And the `$$` is needed so Compose passes `$(...)`
through instead of interpreting it.

Needing two layers of escaping to read a file is a sign the logic belongs in a script. Move it
into one, and give the script real error messages:

- `VERSION` unset
- built artifact missing (was `ansible-galaxy collection build` run?)
- secret not mounted

Each of those is a clear failure instead of an authentication error from Galaxy.

## libexec, not scripts

Helper executables that are invoked by other programs rather than by a person belong in
`libexec/` - that is what the directory means under the FHS. `scripts/` is a catch-all.

```
libexec/publish        <- the wrapper
Dockerfile
compose.yaml
```

```dockerfile
FROM ghcr.io/aursu/rockylinux:<tag>-ansible

COPY --chown=root:root --chmod=0755 libexec/publish /usr/local/libexec/publish

WORKDIR /var/ansible/project
CMD ["/usr/local/libexec/publish"]
```

Setting ownership and mode in the `COPY` itself keeps it to one layer; a separate `RUN chmod`
adds another for nothing.

## Publishing by hand

The manual sequence, if CI is unavailable:

```bash
ansible-galaxy collection build
ansible-galaxy collection publish aursu-general-<version>.tar.gz \
  --api-key "$(cat ~/.ansible/galaxy_token)"
```

`--api-key` must be passed explicitly. `~/.ansible/galaxy_token` is storage only - nothing
reads it automatically, and omitting the flag gives:

```
ERROR! ... (HTTP Code: 401, Message: Authentication credentials were not provided.)
```

## galaxy.yml

Keep `build_ignore` honest - development scaffolding should not ship to users:

```yaml
build_ignore:
  - '*.tar.gz'
  - '.git/'
  - '.github/'
  - '.gitignore'
  - 'compose.yaml'
  - 'Dockerfile'
  - 'libexec/'
  - 'tests/unit/'
```

A collection that depends on another must say so, or it will install and then fail at run time
on a missing import:

```yaml
dependencies:
  "aursu.general": ">=1.0.0"
```

## Version discipline

Galaxy takes the version from `galaxy.yml` and **ignores the git tag**, and it refuses to accept
a version it already holds. Two consequences:

- bump `galaxy.yml` in the same commit the tag points at, or the repository will claim one
  version while Galaxy serves another;
- a tag that does not match `galaxy.yml`, or names an already-published version, cannot publish
  and cannot be fixed by retrying - it has to be re-cut.

Both are checked before the build step by
[`.github/scripts/release_preflight.py`](../../.github/scripts/release_preflight.py), which the
release workflow runs and which you can run by hand before tagging:

```bash
python .github/scripts/release_preflight.py --tag v1.8.0
```

It refuses the release if the tag does not match `galaxy.yml` (a leading `v` is stripped, so
`v1.8.0` and `1.8.0` both work), if Galaxy already holds that version, or if the version is not
valid semver. `ansible-galaxy collection build` does **not** check the version - fed
`version: not-a-version` it produces `aursu-probe-not-a-version.tar.gz` without complaint - so the
rejection lands at Galaxy's import step, which is after the upload and therefore after the tag is
spent. The check uses ansible-core's own `SemanticVersion`, the class Galaxy's dependency resolver
uses, so it is the same notion of valid that will judge the upload. Galaxy being unreachable is a warning, not a refusal: an outage elsewhere is
not evidence that the version is taken, and the publish step fails loudly enough if it is.

Namespace and name come from `galaxy.yml` too, so the script works unchanged in the other
collections. It is a script rather than inline shell for one reason worth stating: the check you
actually want is the one you can run *before* cutting the tag, and inline workflow steps can only
run after.

`--skip-galaxy` checks everything except the network call. Exit codes are `0` clean, `1` a guard
refused the release, `2` the check could not run.

## Optional: a Makefile

The compose invocations are long enough to be worth aliasing, if you prefer `make test` to
remembering flags:

```makefile
.PHONY: test test-modules shell

test:
	docker compose run --rm --remove-orphans tests

test-modules:
	docker compose run --rm --remove-orphans tests pytest -v tests/unit/plugins/modules

shell:
	docker compose run --rm --remove-orphans --entrypoint /bin/bash tests
```

`make shell` drops into the container to run pytest by hand, which is the quickest way to debug
a failing mock.

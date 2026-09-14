# Unit testing

## Why the collection-path import works

Tests import modules by their full collection path even though there is no `ansible_collections`
directory in the repository:

```python
from ansible_collections.aursu.general.plugins.modules import sshd_info
```

This works because of the `pytest-ansible` plugin, visible in pytest's startup banner as
`plugins: ansible-...`. It detects that the tests are running inside a collection, adjusts
`sys.path`, and installs an import hook mapping `ansible_collections.aursu.general` onto the
current directory.

The benefit is that test code looks exactly like production code would on a host where the
collection is installed under `/usr/share/ansible/collections/`.

## Running them

```bash
docker compose run --rm --remove-orphans tests
docker compose run --rm --remove-orphans tests pytest -v tests/unit/plugins/modules
docker compose run --rm --remove-orphans tests pytest -v tests/unit/plugins/modules/test_sshd_info.py
```

The first runs everything. The others override the default command to narrow the scope.

## Do not mock the thing under test

The first version of the `sshd_info` test mocked `SshConfigParser` itself, then asserted that
the module had called it and passed its return value to `exit_json`. That test verifies that
Python can call a function. Break the parser completely and it still passes.

Mock the **boundary**, not the logic: patch the filesystem and `AnsibleModule`, let the real
parser run, and assert on the resulting data.

```python
# worthless
self.assertEqual(mock_parser.parse.call_count, 1)

# meaningful
self.assertEqual(result['Port']['value'], '22')
self.assertEqual(result['Port']['location'], '/etc/ssh/sshd_config')
```

## Use StringIO, not mock_open

`unittest.mock.mock_open` is unreliable for `readlines()` - depending on version it returns an
empty list, so the parser reads an empty file, produces `{}`, and the test fails with a
confusing `KeyError` rather than an I/O error.

`io.StringIO` is a real file object. It supports iteration, `readlines()` and the context
manager protocol.

```python
def _mock_reader(self, filename, *args, **kwargs):
    if filename in self.fs_map:
        return StringIO(self.fs_map[filename])     # fresh stream per open
    raise IOError("File not found in mock fs: %s" % filename)
```

Return a **new** stream on every call: a stream that has been read once is exhausted, and the
parser legitimately opens the same file more than once.

## The four mocks people forget

A silent empty result almost always means one of these was missed. The symptom is identical in
every case - the parser returns `{}` and the assertion fails on a missing key.

**`os.path.abspath`** - on Windows it turns `/etc/ssh/sshd_config` into `C:\etc\ssh\sshd_config`,
which is not a key in the virtual filesystem. Force it to identity:

```python
self.mock_abspath.side_effect = lambda x: x
```

**`os.path.isfile`** - the guard is `if not os.path.exists(p) or not os.path.isfile(p): return`.
Mocking only `exists` leaves `isfile` hitting the real disk, where the file is absent, so the
parser returns before reading anything. This one is genuinely hard to spot: a `print` before
the guard fires and a `print` after it does not.

**`glob.glob`** - `Include` resolution goes through it. A simple map lookup is usually enough,
with an explicit entry for each wildcard pattern:

```python
def _mock_glob(self, pattern):
    if pattern == "/etc/ssh/conf.d/*.conf":
        return ["/etc/ssh/conf.d/01-custom.conf"]
    return [pattern] if pattern in self.fs_map else []
```

**`os.path.exists` in two places** - both the module (validating its argument) and the parser
(walking includes) call it, and they are different import sites. Patch both.

### Patch where the name is used

`ssh_parser` imports `io`, `os` and `glob` itself, so those are patched at
`...module_utils.ssh_parser.io.open`, not at `io.open`. Keep the two module paths in constants:

```python
PARSER_MOD = 'ansible_collections.aursu.general.plugins.module_utils.ssh_parser'
MODULE_MOD = 'ansible_collections.aursu.general.plugins.modules.sshd_info'
```


### Testing wildcard includes

The simple mock above only matches exact strings, so `Include conf.d/*.conf` returns nothing -
the pattern is not a key in the map. For tests that exercise glob expansion, teach the map to
hold either a file's content (a string) or a pattern's expansion (a list):

```python
self.fs_map = {
    # the main file
    "/etc/ssh/sshd_config": u"Include /etc/ssh/conf.d/*.conf\n",

    # a pattern, mapped explicitly to what it expands to
    "/etc/ssh/conf.d/*.conf": [
        "/etc/ssh/conf.d/01-a.conf",
        "/etc/ssh/conf.d/02-b.conf",
    ],

    # and the content of those files, for io.open
    "/etc/ssh/conf.d/01-a.conf": u"Port 2222\n",
    "/etc/ssh/conf.d/02-b.conf": u"PermitRootLogin yes\n",
}

def _mock_glob(self, pattern):
    value = self.fs_map.get(pattern)
    if isinstance(value, list):
        return value                 # a pattern: return its expansion
    if pattern in self.fs_map:
        return [pattern]             # an exact path: glob returns it as a one-item list
    return []                        # no match
```

This is explicit mapping rather than real glob semantics - you state what each pattern expands
to instead of reimplementing `fnmatch`. It keeps the ordering under the test's control, which
matters because include order decides which value wins.

## Set up patches in setUp, not as decorators

Six or seven `@patch` decorators on one test method become unreadable, and the argument order
is reversed relative to the decorator order - a trap every time a patch is added in the middle.

Start them in `setUp` and register cleanup:

```python
def _apply_patch(self, target):
    patcher = patch(target)
    mock_obj = patcher.start()
    self.addCleanup(patcher.stop)      # runs even if the test fails
    return mock_obj
```

`addCleanup` is the reason to prefer this over a manual `tearDown`: patches are reverted even
when the test raises, so one failure cannot poison the rest of the suite.

The test method then contains only the scenario:

```python
def test_full_parsing_logic(self):
    sshd_info.main()

    if self.mock_module_instance.fail_json.called:
        self.fail("Module failed: %s" % self.mock_module_instance.fail_json.call_args)

    _, kwargs = self.mock_module_instance.exit_json.call_args
    result = kwargs.get('sshd_config')
    self.assertEqual(result['Port']['value'], '22')
```

Checking `fail_json.called` first turns "the assertion found `{}`" into the actual error
message.

## Mocking AnsibleModule is not optional

For unit tests the real class is unusable:

- `exit_json` and `fail_json` end in `sys.exit()`, which stops the whole run at the first test;
- it reads its arguments from `sys.argv` or stdin, so every test would have to fabricate an
  argument file;
- it prints its result to stdout, so assertions would mean capturing and re-parsing JSON.

Mock the class, set `.params` on the instance, and assert against `exit_json` / `fail_json`
calls.

## Testing a module that writes

The writer needs one more layer: intercept what is written before `atomic_move` is called.
Patch `tempfile.mkstemp` to return a fixed handle and `os.fdopen` to hand back a `StringIO`
that the test keeps a reference to. Then assert on its contents, and on the destinations passed
to `module.atomic_move` to confirm which files were touched.

## Scenarios worth covering

For the parser: first match wins within one file; the same across an `Include`; Match blocks
with the same condition merged from two files; `Include` inside a `Match` block inheriting the
scope; `Match All` resetting to global; a circular include terminating rather than hanging.

For the writer: the seven contract behaviours listed in
[../design/config-writer.md](../design/config-writer.md).

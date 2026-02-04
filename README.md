# Ansible Collection - aursu.general

Documentation for the collection.

## **Goal**

There is an Ansible module named `aursu.general.lvm_info` that acts like `community.general.parted`, but for **LVM introspection** — returning structured info about:

- **PVs** (Physical Volumes)
- **VGs** (Volume Groups)
- **LVs** (Logical Volumes)

---

## **Module Input (Request)**

This is a module that accepts:

### Required/Optional arguments:

| Option | Type | Description |
|--------|------|-------------|
| `filter` | str (optional) | One of `pvs`, `vgs`, `lvs` (what LVM info to retrieve) |
| `unit` | str (optional, default=`m`) | Passed to LVM's `--units` option to control size formatting (e.g., `m` = mebibytes, `G` = gigabytes, `r` = human-readable with `<`) |

So a task might look like:

```yaml
- name: Get all logical volumes in gigabytes
  aursu.general.lvm_info:
    filter: lvs
    unit: G
```

---

## **What the Module Does (Internals)**

The module:

1. Accepts the input (`filter`, `unit`)
2. Builds a command like:
   ```bash
   lvs --units G --reportformat json
   ```
3. Executes it using `subprocess`
4. Parses the **JSON output** using `json.loads(...)`
5. Returns a dictionary like:
   ```json
   {
     "lv": [
       { "lv_name": "root", "size": "20.00g", ... }
     ],
     "vg": [],
     "pv": []
   }
   ```

Depending on what was requested.

---

## **Module Output (Return)**

The module returns structured data (under `result.lv`, `result.vg`, `result.pv`) matching the real structure of LVM commands.

For example:

```yaml
lv:
  - lv_name: "data"
    vg_name: "vg0"
    lv_size: "100.00g"
vg:
  - vg_name: "vg0"
    pv_count: "1"
    lv_count: "2"
pv:
  - pv_name: "/dev/sda1"
    vg_name: "vg0"
```

---

## **Why this matters**

With this module, users get:

- **Reliable, structured LVM info** directly in playbooks
- A consistent output schema — no `shell: pvs | awk` hacks
- An extensible collection (you could later add RAID info, ZFS, etc.)

# **Documentation-ready summary** of what the `aursu.general.lvm_info` module does

---

## Overview

The `aursu.general.lvm_info` module provides structured information about LVM components on a Linux system. It serves as an information-gathering module, returning data about physical volumes (PVs), volume groups (VGs), and logical volumes (LVs) using native system tools such as `pvs`, `vgs`, and `lvs`.

---

## Module Parameters

| Name   | Required | Type | Default | Description |
|--------|----------|------|---------|-------------|
| `filter` | No | string | `pvs` | Specifies which type of LVM object to query: `pvs`, `vgs`, or `lvs`. |
| `unit`   | No | string | `m`   | Defines the size unit to use, passed directly to the LVM `--units` option. Supports values like `m`, `G`, `r`, etc. See `--units` section below for details. |

---

## Functionality

Based on the `filter` value, the module:

- Executes the appropriate LVM command (`pvs`, `vgs`, or `lvs`) with `--reportformat json` and `--units <unit>`.
- Parses the output into structured Python data.
- Returns the data in a dictionary format under one of the following keys: `pv`, `vg`, or `lv`.

All keys are always present in the result and contain either a list of entries or an empty list.

---

## Return Structure

| Key | Type | Description |
|-----|------|-------------|
| `pv` | list of dicts | Physical volumes information (from `pvs`) |
| `vg` | list of dicts | Volume group information (from `vgs`) |
| `lv` | list of dicts | Logical volume information (from `lvs`) |

Each object contains relevant attributes as reported by the LVM tool in JSON mode.

---

## Units

The module supports the full range of units accepted by LVM's `--units` option:

```
--units [Number]r|R|h|H|b|B|s|S|k|K|m|M|g|G|t|T|p|P|e|E
```

| Unit | Base | Description |
|------|------|-------------|
| `r`, `R` | binary/decimal | Human-readable with `<` rounding indicator |
| `h`, `H` | binary/decimal | Human-readable |
| `b`, `B` | bytes          | Bytes |
| `s`, `S` | sectors        | Sectors |
| `k`, `K` | KiB / kB       | Kilobytes |
| `m`, `M` | MiB / MB       | Megabytes (default = `m`) |
| `g`, `G` | GiB / GB       | Gigabytes |
| `t`, `T` | TiB / TB       | Terabytes |
| `p`, `P` | PiB / PB       | Petabytes |
| `e`, `E` | EiB / EB       | Exabytes |

Lowercase = base-2 (binary), uppercase = base-10 (decimal).
Custom units (e.g. `--units 3M`) are also accepted by LVM but are not supported in this module at this time.

## aursu.general.dev_info

This module gathers information about a file system object such as a block device, regular file, socket, FIFO, or symbolic link.
It uses the following sources:
- `os.stat` for file metadata
- `blkid --output export` for block device attributes (if applicable)
- `findmnt -J` for mount information (if applicable)

### Parameters

| Name | Required | Type | Description |
|------|----------|------|-------------|
| dev  | yes      | path | Path to the file system object. Aliases: `device`. |

### Return values

| Key        | Type   | Description |
|------------|--------|-------------|
| is_exists  | bool   | Whether the path exists. |
| stat       | dict   | POSIX stat(2) fields like `mode`, `uid`, `size`, etc. |
| stat.error | string | Present only if `os.stat()` failed. |
| filetype   | string | File type in `ls -l` style: `b`, `c`, `d`, `-`, `l`, `p`, `s`. |
| blkid      | dict   | Key-value output from `blkid --output export` (only for block devices). |
| mount      | dict   | Mount point info from `findmnt -J` (only for block devices). |

### Example

```yaml
- name: Gather info about /dev/sdb1
  aursu.general.dev_info:
    dev: /dev/sdb1
  register: dev_info
```

# How to Publish an Ansible Content Collection

This is a step-by-step guide to creating and publishing an Ansible Content Collection. It follows the official Red Hat documentation:
[Creating and publishing Ansible Content Collections](https://developers.redhat.com/learning/learn:ansible:getting-started-ansible-content-collections/resource/resources:creating-and-publishing-ansible-content-collections)

---

## Steps

### 1. **Create an Ansible Galaxy Account**

If you don’t already have one, visit [https://galaxy.ansible.com](https://galaxy.ansible.com) and sign up.

> Ansible Galaxy uses GitHub for authentication.

---

### 2. **Initialize a New Collection**

Run the following command to scaffold a new collection:

```bash
ansible-galaxy collection init <namespace>-<collection_name>
```

This will generate a standard directory structure, e.g. `aursu-general/`.

---

### 3. **Configure Metadata**

Edit the following files:

* `galaxy.yml`: Set metadata like `namespace`, `name`, `version`, `authors`, and `description`.
* `meta/runtime.yml`: (Optional) Define supported Ansible Core versions.

---

### 4. **Build the Collection**

Use the build command to generate a `.tar.gz` archive:

```bash
ansible-galaxy collection build
```

The output will be something like:

```
aursu-general-1.2.0.tar.gz
```

---

### 5. **Generate an API Token**

Go to your Galaxy user settings → **"API tokens"** and create a new token. Save it locally:

```bash
echo "your_token_here" > ~/.ansible/galaxy_token
```

> This file is used only to **store** the token. It is not picked up automatically during publishing.

---

### 6. **Publish the Collection**

Use the following command to publish the archive:

```bash
ansible-galaxy collection publish aursu-general-1.2.0.tar.gz --api-key $(cat ~/.ansible/galaxy_token)
```

> Do **not** rely on `~/.ansible/galaxy_token` alone. Without explicitly passing `--api-key`, the command will fail with:

```
ERROR! Error when publishing collection to default (https://galaxy.ansible.com/api/) (HTTP Code: 401, Message: Authentication credentials were not provided. Code: not_authenticated)
```

---

### 7. **Install or Upgrade the Collection**

Once published, you can install or update the collection locally with:

```bash
ansible-galaxy collection install aursu.general --upgrade
```

# Debugging a Custom Ansible Module on the Target Host

This guide explains how to manually debug a custom Ansible module by preserving and interacting with the temporary files on the **target host**.

---

## 1. Clean Up Previous Temporary Files

Before you begin, remove any leftover temp files from earlier runs to avoid conflicts:

```bash
ssh deployuser@node01.example.net
rm -rf /home/deployuser/.ansible/tmp/*
```

> Note: Even with `become: true`, Ansible stores temporary files in the **SSH user’s home directory**, not under `/root`.

---

## 2. Create a Minimal Playbook

To isolate module behavior, create a focused playbook containing only the task to debug:

```yaml
# playbooks/dev_info_debug.yml
- name: Run single task for module debugging
  hosts: all
  become: true
  tasks:
    - name: Get device info for /dev/mapper/data-data1
      aursu.general.dev_info:
        dev: /dev/mapper/data-data1
      register: dev_mapper_info
```

> * Use concrete values, not Jinja2 expressions.
> * Keep the playbook minimal.

---

## 3. Run the Playbook with Temp File Retention

To preserve the temporary module files Ansible generates, run the playbook with:

```bash
ANSIBLE_KEEP_REMOTE_FILES=1 ansible-playbook playbooks/dev_info_debug.yml --limit kubernetes_ce -vvv
```

* `-vvv`: Enables verbose output (required to see module paths)
* `--limit`: Restrict run to a specific host or group

---

## 4. Locate the Module Wrapper Path

In the verbose output, find the command Ansible runs on the target:

```
<node01.example.net> EXEC ssh -o User="deployuser" node01.example.net '/usr/bin/python3.12 /home/deployuser/.ansible/tmp/.../AnsiballZ_dev_info.py'
```

Extract:

* Python path: `/usr/bin/python3.12`
* Module path: `/home/deployuser/.ansible/tmp/.../AnsiballZ_dev_info.py`

---

## 5. Unpack the Module Using `explode`

On the **target host**, unpack the module:

```bash
/usr/bin/python3.12 /home/deployuser/.ansible/tmp/.../AnsiballZ_dev_info.py explode
```

Example output:

```
Module expanded into:
/home/deployuser/.ansible/tmp/.../debug_dir
```

The `debug_dir` will contain:

* Actual Python module source
* Argument JSON (`args`)
* Runtime files (`__main__.py`, etc.)

---

## 6. Inspect or Modify the Module Source

Navigate to the extracted module source:

```bash
ls -la debug_dir/ansible_collections/aursu/general/plugins/modules/dev_info.py
```

Insert debug lines like:

```python
print("DEBUG: received parameters:", module.params)
```

> `print()` output will appear when manually executing the module.

---

## 7. Run the Module Manually with `execute`

Once modified, run it manually:

```bash
/usr/bin/python3.12 /home/deployuser/.ansible/tmp/.../AnsiballZ_dev_info.py execute
```

Example output:

```json
DEBUG: received parameters: {"dev": "/dev/mapper/data-data1"}

{
  "changed": false,
  "is_exists": true,
  "stat": {...},
  "filetype": "b",
  "blkid": {...},
  "invocation": {
    "module_args": {"dev": "/dev/mapper/data-data1"}
  }
}
```

> This runs the module in isolation — no need to re-run the entire playbook for every change.

---

## Summary

| Step | Description                           |
| ---- | ------------------------------------- |
| 1    | Clean old temp files                  |
| 2    | Create minimal playbook               |
| 3    | Run playbook with `KEEP_REMOTE_FILES` |
| 4    | Find `AnsiballZ_*.py` path            |
| 5    | Unpack it with `explode`              |
| 6    | Modify the real module code           |
| 7    | Run with `execute` and observe output |

## Testing

This collection includes a Docker Compose configuration to simplify running unit tests (in an isolated environment).

### Run all unit tests

To run the entire test suite, simply execute:

```
docker compose run --rm --remove-orphans tests
```

### Run specific tests

You can override the default command to run tests for a specific path or file.
For example, to test only the modules:

```
docker compose run --rm --remove-orphans tests pytest -v tests/unit/plugins/modules

```

Or to run a specific test file:

```
docker compose run --rm --remove-orphans tests pytest -v tests/unit/plugins/modules/test_sshd_info.py
```
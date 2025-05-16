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

# Publish an Ansible Content Collection

A step-by-step guide to publishing an Ansible Content Collection, based on the official Red Hat documentation: [Creating and publishing Ansible Content Collections](https://developers.redhat.com/learning/learn:ansible:getting-started-ansible-content-collections/resource/resources:creating-and-publishing-ansible-content-collections)

### Steps:

1. **Create an Ansible Galaxy account**  
   If you don’t have one yet, go to [https://galaxy.ansible.com](https://galaxy.ansible.com) and sign up. Galaxy uses GitHub for authentication.

2. **Initialize a new collection**  
   Use the command:
   ```bash
   ansible-galaxy collection init <namespace>-<collection_name>
   ```

3. **Configure the collection**  
   - Edit `galaxy.yml` to define metadata (namespace, name, version, etc.).
   - Optionally, set `meta/runtime.yml` to define supported Ansible Core versions.

4. **Build the collection artifact**  
   Create a distributable archive:
   ```bash
   ansible-galaxy collection build
   ```
   This will generate a `.tar.gz` file like `aursu-general-1.2.0.tar.gz`.

5. **Create an Ansible Galaxy API token**  
   Go to your Galaxy user settings and generate an API token. Save it in a file:
   ```bash
   echo "your_token_here" > ~/.ansible/galaxy_token
   ```

6. **Publish the collection (important!)**  
   To publish, **you must explicitly use the `--api-key` option**.  
   The presence of `~/.ansible/galaxy_token` alone **does not work**, and will result in a 401 error:
   ```
   ERROR! Error when publishing collection to default (https://galaxy.ansible.com/api/) (HTTP Code: 401, Message: Authentication credentials were not provided. Code: not_authenticated)
   ```

   The only working command:
   ```bash
   ansible-galaxy collection publish aursu-general-1.2.0.tar.gz --api-key $(cat ~/.ansible/galaxy_token)
   ```

# Debug on target host

### Clean Up Ansible Temporary Files on the Target Host

Before debugging an Ansible module manually, it's recommended to clear the temporary files left from previous runs. This ensures a clean environment and avoids conflicts.

Suppose the Ansible control node connects to the target host `node01.example.net` using the user `deployuser`. Then, on the **target host**, run:

```bash
ssh deployuser@node01.example.net
rm -rf /home/deployuser/.ansible/tmp/*
```

> Note: Even if Ansible escalates privileges using `become: true` (e.g. to `root`), the temporary files are located in the home directory of the SSH user (`deployuser`), not under `/root`.

### Create a Minimal Playbook to Debug the Module

To isolate and debug a specific Ansible module, create a minimal playbook that contains only the module call and the input data you want to test.

Suppose you want to debug the custom module `aursu.general.dev_info` with the device `/dev/mapper/data-data1`. Your playbook may look like this:

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

> Note:
>
> * Make sure to provide **actual input values**, not Jinja2 variables unless needed.
> * This playbook should be kept as simple as possible to focus on module behavior.

### Run the Playbook with `ANSIBLE_KEEP_REMOTE_FILES=1` to Preserve Module Files

To debug a module manually, you need to preserve the temporary files that Ansible uploads to the target host during execution. This can be done by setting the environment variable `ANSIBLE_KEEP_REMOTE_FILES=1`.

Suppose your inventory group or host is named `kubernetes_ce`. Then run the playbook like this:

```bash
ANSIBLE_KEEP_REMOTE_FILES=1 ansible-playbook playbooks/dev_info_debug.yml --limit kubernetes_ce -vvv
```

> The `-vvv` option is important — it enables verbose output that will show the exact module path and the command Ansible runs on the target.

> Be sure to run this command from the Ansible control node (your workstation or CI environment).


### Locate the Module File on the Target Host

In the verbose output from `ansible-playbook -vvv`, look for a line that shows the full command Ansible runs on the target host. This line includes the path to the temporary Python module wrapper used during execution.

Example (simplified):

```text
<node01.example.net> EXEC ssh -o User="deployuser" node01.example.net '/usr/bin/python3.12 /home/deployuser/.ansible/tmp/ansible-tmp-XXXXXXXXXX-XXXX-XXXXXXXXXXXXXX/AnsiballZ_dev_info.py'
```

From this output you can extract:

* **Python interpreter**: `/usr/bin/python3.12`
* **Module path**: `/home/deployuser/.ansible/tmp/ansible-tmp-.../AnsiballZ_dev_info.py`

> This is the script you will execute manually for debugging in the next step.

### Unpack the Module on the Target Host

To inspect the contents of the Ansible module and debug it manually, you need to **unpack** the `AnsiballZ_*.py` wrapper file on the target host.

Use the `explode` argument to extract its contents:

```bash
/usr/bin/python3.12 /home/deployuser/.ansible/tmp/ansible-tmp-XXXXXXXXXX-XXXX-XXXXXXXXXXXXXX/AnsiballZ_dev_info.py explode
```

Example:

```bash
/usr/bin/python3.12 /home/deployuser/.ansible/tmp/ansible-tmp-1747438014.5293243-5508-26587107288771/AnsiballZ_dev_info.py explode
```

After running the command, you'll see output like:

```text
Module expanded into:
/home/deployuser/.ansible/tmp/ansible-tmp-1747438014.5293243-5508-26587107288771/debug_dir
```

Inside `debug_dir` you’ll find:

* The actual module code (e.g. `dev_info.py`)
* A JSON file with arguments (`args`)
* Supporting Ansible files (`__main__.py`, etc.)

> **This unpacked directory is where you can run or modify the module code directly for debugging purposes.**

### Locate and Modify the Actual Module Code

After unpacking the module, you can now inspect and modify the actual Python source file.

Inside the extracted `debug_dir`, the module is located in the standard Ansible Collection path:

```text
debug_dir/ansible_collections/<namespace>/<collection>/plugins/modules/<module>.py
```

For example:

```bash
/home/deployuser/.ansible/tmp/ansible-tmp-XXXXXXXXXX-XXXX-XXXXXXXXXXXXXX/debug_dir/ansible_collections/aursu/general/plugins/modules/dev_info.py
```

Check it:

```bash
ls -la /home/deployuser/.ansible/tmp/ansible-tmp-XXXXXXXXXX/debug_dir/ansible_collections/aursu/general/plugins/modules/dev_info.py
```

Output might look like:

```text
-rw-r--r-- 1 root root 5889 May 16 23:27 /home/deployuser/.ansible/tmp/.../dev_info.py
```

Now you can open the file and insert any debug logic you need, such as:

```python
print("DEBUG: received parameters:", module.params)
```

> These `print()` statements will show up in the module's stdout when you run it manually (in the next step).

### Run the Module Manually with `execute` to Test Changes

After making your modifications (e.g., adding debug output via `print()`), you can manually execute the unpacked module using the `execute` argument:

```bash
/usr/bin/python3.12 /home/deployuser/.ansible/tmp/ansible-tmp-XXXXXXXXXX-XXXX-XXXXXXXXXXXXXX/AnsiballZ_dev_info.py execute
```

Example output:

```text
DEBUG: received parameters: {'dev': '/dev/mapper/data-data1'}

{"changed": false, "is_exists": true, "stat": {...}, "filetype": "b", "blkid": {...}, "invocation": {"module_args": {"dev": "/dev/mapper/data-data1"}}}
```

> This runs the module exactly as Ansible would, but now with your custom debug statements printed to the console.

> You can now iteratively modify the module source, re-run it with `execute`, and observe the results — no need to re-run the playbook each time.

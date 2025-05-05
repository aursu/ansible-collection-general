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

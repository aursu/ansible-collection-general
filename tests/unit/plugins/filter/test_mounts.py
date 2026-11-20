import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.aursu.general.plugins.filter.mounts import validate_mount_point

# Shape of ansible_facts.mounts (trimmed to the keys that matter).
MOUNTS = [
    {"mount": "/", "device": "/dev/nvme0n1p3", "fstype": "xfs"},
    {"mount": "/boot", "device": "/dev/nvme0n1p2", "fstype": "ext4"},
    {"mount": "/var/lib/docker", "device": "/dev/mapper/data-docker", "fstype": "xfs"},
]


def test_a_mount_point_passes():
    assert validate_mount_point(MOUNTS, "/var/lib/docker") is True


def test_trailing_slash_and_dots_are_normalised():
    assert validate_mount_point(MOUNTS, "/var/lib/./docker/") is True


def test_a_directory_on_the_root_filesystem_fails_naming_the_holder():
    with pytest.raises(AnsibleFilterError, match=r"^/srv/workspace is not a mount point: it is on / \(/dev/nvme0n1p3\)\.$"):
        validate_mount_point(MOUNTS, "/srv/workspace")


def test_a_subdirectory_of_a_mount_is_not_a_mount_point():
    with pytest.raises(AnsibleFilterError, match=r"it is on /var/lib/docker \(/dev/mapper/data-docker\)"):
        validate_mount_point(MOUNTS, "/var/lib/docker/volumes")


def test_prefixes_compare_by_component():
    # /var/lib/docker2 is not under /var/lib/docker; it is on /.
    with pytest.raises(AnsibleFilterError, match=r"it is on / \("):
        validate_mount_point(MOUNTS, "/var/lib/docker2")


def test_the_later_of_two_entries_for_one_mount_point_wins():
    mounts = MOUNTS + [{"mount": "/var/lib/docker", "device": "tmpfs", "fstype": "tmpfs"}]
    with pytest.raises(AnsibleFilterError, match=r"it is on /var/lib/docker \(tmpfs\)"):
        validate_mount_point(mounts, "/var/lib/docker/x")


def test_an_empty_table_fails_clearly():
    with pytest.raises(AnsibleFilterError, match="no mount in the table holds it"):
        validate_mount_point([], "/var/lib/docker")


@pytest.mark.parametrize("mounts, path, message", [
    ({"mount": "/"}, "/var", "to be a list"),
    (MOUNTS, "var/lib/docker", "Expected an absolute path"),
    (MOUNTS, None, "Expected an absolute path"),
])
def test_malformed_input_is_refused(mounts, path, message):
    with pytest.raises(AnsibleFilterError, match=message):
        validate_mount_point(mounts, path)

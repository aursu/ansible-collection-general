import pytest
from ansible.errors import AnsibleFilterError

from ansible_collections.aursu.general.plugins.filter.packages import (
    validate_package_names,
    validate_package_pins,
)

PINS = {
    "docker-ce": "5:29.9.3-1~ubuntu.24.04~noble",
    "containerd.io": "2.4.2-4~ubuntu.24.04~noble",
}


def test_pins_with_exact_version_strings_pass():
    assert validate_package_pins(PINS) is True


@pytest.mark.parametrize("version, message", [
    (None, r"got None\.$"),                      # `docker-ce:` with no value
    ("", r"got ''\."),
    ("   ", r"got '   '\."),
    (0.39, r"got 0\.39\. Quote it in YAML\."),   # unquoted in YAML
    (29, r"got 29\. Quote it in YAML\."),
    (["5:29.9.3"], r"got \['5:29\.9\.3'\]\."),
])
def test_a_version_that_is_not_a_non_empty_string_is_refused_naming_the_package(version, message):
    with pytest.raises(AnsibleFilterError, match=r"'docker_packages\['docker-ce'\]' must be an exact version string, " + message):
        validate_package_pins({"docker-ce": version}, "docker_packages")


@pytest.mark.parametrize("pins", [{}, None, [], "docker-ce=5:29"])
def test_pins_must_be_a_non_empty_map(pins):
    with pytest.raises(AnsibleFilterError, match="must be a non-empty map"):
        validate_package_pins(pins)


def test_an_empty_package_name_is_refused():
    with pytest.raises(AnsibleFilterError, match="empty or non-string package name"):
        validate_package_pins({"": "1.0"})


@pytest.mark.parametrize("value", ["lvm2", ["lvm2", "parted"], []])
def test_names_pass(value):
    assert validate_package_names(value) is True


@pytest.mark.parametrize("value", [None, "", 42, ["lvm2", ""], ["lvm2", None], {"lvm2": "1"}])
def test_malformed_names_are_refused(value):
    with pytest.raises(AnsibleFilterError, match=r"'base' must be a package name or a list of package names"):
        validate_package_names(value, "base")

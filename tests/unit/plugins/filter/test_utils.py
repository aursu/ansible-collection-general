from ansible_collections.aursu.general.plugins.filter import utils

def test_all_attr_equals_true_identical():
    data = [{"status": "ok"}, {"status": "ok"}]
    assert utils.all_attr_equals(data, "status", "ok") is True

def test_all_attr_equals_false_one_differs():
    data = [{"status": "ok"}, {"status": "fail"}]
    assert utils.all_attr_equals(data, "status", "ok") is False

def test_all_attr_equals_false_missing_key():
    data = [{"status": "ok"}, {"state": "ok"}]
    assert utils.all_attr_equals(data, "status", "ok") is False

def test_all_attr_equals_empty_list():
    data = []
    # all() returns True on empty iterable by definition
    assert utils.all_attr_equals(data, "status", "ok") is True

def test_all_attr_equals_mixed_data_types():
    data = [{"val": 1}, {"val": "1"}, {"val": True}]
    assert utils.all_attr_equals(data, "val", 1) is False

def test_any_attr_not_true_varied():
    data = [{"mode": "auto"}, {"mode": "manual"}, {"mode": "auto"}]
    assert utils.any_attr_not(data, "mode", "auto") is True

def test_any_attr_not_false_all_match():
    data = [{"role": "admin"}, {"role": "admin"}]
    assert utils.any_attr_not(data, "role", "admin") is False

def test_any_attr_not_true_missing_key():
    data = [{"id": 1}, {"uuid": 1}]
    assert utils.any_attr_not(data, "id", 1) is True

def test_any_attr_not_empty_list():
    data = []
    assert utils.any_attr_not(data, "id", 1) is False

def all_attr_equals(data, attr, expected):
    """
    Returns True only if ALL items have data[attr] == expected.
    """
    return all(item.get(attr) == expected for item in data)

def any_attr_not(data, attr, expected):
    """
    Returns True if ANY item in list of dicts has data[attr] different than expected.
    """
    return not all_attr_equals(data, attr, expected)

class FilterModule(object):
    def filters(self):
        return {
            "any_attr_not": any_attr_not,
            "all_attr_equals": all_attr_equals,
        }

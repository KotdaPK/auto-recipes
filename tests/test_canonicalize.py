from src.dedup.canonicalize import canonicalize, ALIAS_MAP


def test_descriptor_removal_and_alias():
    assert canonicalize("Fresh chopped Roma tomatoes") == "tomato"
    assert canonicalize("Extra virgin olive oil") == "olive oil"
    assert canonicalize("scallions, finely chopped") == "green onion"

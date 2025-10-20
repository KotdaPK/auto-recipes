from src.dedup.match import match_or_create


class DummyIndex:
    """A tiny index with a predictable nearest() implementation for tests."""

    def __init__(self, mapping=None):
        # mapping: query -> (name, score)
        self.mapping = mapping or {}

    def nearest(self, query, topk: int = 1):
        return self.mapping.get(query, ("", 0.0))


def test_matcher_threshold_behavior():
    names = {"tomato", "olive oil", "green onion"}
    # DummyIndex returns nothing (low score) for unknowns
    idx = DummyIndex()

    status, name, score = match_or_create("Roma tomatoes", names, idx, threshold=0.5)
    # canonicalization maps 'Roma tomatoes' -> 'tomato', which is in existing names
    assert status == "existing"
    assert name == "tomato"

    status2, name2, score2 = match_or_create("unicorn dust", names, idx, threshold=0.99)
    assert status2 == "new"

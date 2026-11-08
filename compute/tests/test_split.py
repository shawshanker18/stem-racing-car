from dispatch import split


def test_split_covers_every_id_once_and_respects_weights():
    ids = list(range(100))
    out = split(ids, {"a": 38, "b": 20, "c": 20})
    got = sorted(i for v in out.values() for i in v)
    assert got == ids
    assert [len(out[u]) for u in ("a", "b", "c")] == [49, 26, 25] or \
           sorted(len(v) for v in out.values()) == [25, 26, 49]
    # interleaved: the first 6 ids are not all on one account
    assert len({u for u, v in out.items() for i in v if i < 6}) >= 2


def test_split_single_account():
    assert split([0, 1, 2], {"a": 20}) == {"a": [0, 1, 2]}

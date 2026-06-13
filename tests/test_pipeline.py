"""Phase 0 smoke tests — pipeline round-trips without crashing.

Phase 2+ will replace these stubs with real jyutping assertions.
"""
from canto_g2p import Pipeline


def test_empty_string():
    p = Pipeline()
    assert p.convert("") == ""


def test_passthrough_ascii():
    p = Pipeline()
    result = p.convert("hello")
    assert isinstance(result, str)
    assert len(result) > 0


def test_cantonese_chars_return_string():
    p = Pipeline()
    result = p.convert("你好嘅")
    assert isinstance(result, str)


def test_batch_same_as_single():
    p = Pipeline()
    inputs = ["你好", "香港", "hello"]
    batch = p.convert_batch(inputs)
    single = [p.convert(t) for t in inputs]
    assert batch == single


def test_batch_empty_list():
    p = Pipeline()
    assert p.convert_batch([]) == []

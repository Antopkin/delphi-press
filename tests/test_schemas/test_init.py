"""Smoke test for src.schemas.__init__ — all exports are accessible."""

import src.schemas


def test_all_exports_accessible():
    for name in src.schemas.__all__:
        assert hasattr(src.schemas, name), f"{name} is listed in __all__ but not accessible"


def test_all_exports_count():
    assert len(src.schemas.__all__) == 57

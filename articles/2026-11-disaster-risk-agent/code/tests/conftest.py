from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never hit the network."""
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network access in tests")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

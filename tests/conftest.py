import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(**overrides) -> TestClient:
    settings = Settings(
        database_url="sqlite:///:memory:",
        rate_limit_capacity=overrides.pop("rate_limit_capacity", 1000),
        rate_limit_refill_per_sec=overrides.pop("rate_limit_refill_per_sec", 100.0),
        **overrides,
    )
    # follow_redirects=False so tests can assert on the redirect itself.
    return TestClient(create_app(settings), follow_redirects=False)


@pytest.fixture
def client() -> TestClient:
    return make_client()

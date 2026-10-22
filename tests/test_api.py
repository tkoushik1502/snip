from datetime import timedelta

from sqlalchemy import update

from app.models import Link, utcnow
from tests.conftest import make_client


def create(client, **body):
    body.setdefault("url", "https://example.com/some/long/path")
    return client.post("/api/links", json=body)


def test_create_and_redirect(client):
    res = create(client)
    assert res.status_code == 201
    data = res.json()
    assert len(data["code"]) == 7
    assert data["short_url"].endswith("/" + data["code"])
    assert data["click_count"] == 0

    redirect = client.get("/" + data["code"])
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://example.com/some/long/path"


def test_clicks_are_counted_with_referrer(client):
    code = create(client).json()["code"]
    client.get("/" + code, headers={"referer": "https://news.ycombinator.com/"})
    client.get("/" + code, headers={"referer": "https://news.ycombinator.com/"})
    client.get("/" + code)

    stats = client.get(f"/api/links/{code}/stats").json()
    assert stats["total_clicks"] == 3
    assert stats["link"]["click_count"] == 3
    assert len(stats["clicks_by_day"]) == 30
    assert stats["clicks_by_day"][-1]["clicks"] == 3
    assert stats["top_referrers"][0] == {"referrer": "https://news.ycombinator.com/", "clicks": 2}
    assert {"referrer": "direct", "clicks": 1} in stats["top_referrers"]


def test_custom_alias(client):
    res = create(client, alias="my-link")
    assert res.status_code == 201
    assert res.json()["code"] == "my-link"
    assert client.get("/my-link").status_code == 302


def test_duplicate_alias_conflicts(client):
    assert create(client, alias="taken").status_code == 201
    res = create(client, alias="taken")
    assert res.status_code == 409


def test_reserved_and_malformed_aliases_rejected(client):
    for alias in ["api", "docs", "ab", "has space", "x" * 33, "bad/slash"]:
        assert create(client, alias=alias).status_code == 422, alias


def test_invalid_url_rejected(client):
    assert create(client, url="not a url").status_code == 422
    assert create(client, url="ftp://example.com/file").status_code == 422
    assert create(client, url="javascript:alert(1)").status_code == 422


def test_unknown_code_404(client):
    assert client.get("/nope123").status_code == 404
    assert client.get("/api/links/nope123/stats").status_code == 404


def test_expired_link_returns_410(client):
    code = create(client, expires_in_hours=1).json()["code"]
    assert client.get("/" + code).status_code == 302

    # Move the expiry into the past instead of waiting an hour.
    with client.app.state.sessionmaker() as db:
        db.execute(
            update(Link).where(Link.code == code).values(expires_at=utcnow() - timedelta(seconds=1))
        )
        db.commit()

    assert client.get("/" + code).status_code == 410


def test_list_links_newest_first(client):
    create(client, alias="first")
    create(client, alias="second")
    codes = [link["code"] for link in client.get("/api/links").json()]
    assert codes == ["second", "first"]


def test_delete_link(client):
    create(client, alias="gone")
    assert client.delete("/api/links/gone").status_code == 204
    assert client.get("/gone").status_code == 404


def test_rate_limit_returns_429_with_retry_after():
    client = make_client(rate_limit_capacity=2, rate_limit_refill_per_sec=0.01)
    assert create(client).status_code == 201
    assert create(client).status_code == 201
    res = create(client)
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) >= 1


def test_code_collision_is_retried(client, monkeypatch):
    first = create(client).json()["code"]
    # Force the generator to return the existing code once, then a fresh one.
    codes = iter([first, "fresh01"])
    monkeypatch.setattr("app.main.random_code", lambda length: next(codes))
    res = create(client)
    assert res.status_code == 201
    assert res.json()["code"] == "fresh01"


def test_dashboard_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "Snip" in page.text

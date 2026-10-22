import os
from dataclasses import dataclass, field


def _normalize_db_url(url: str) -> str:
    # Hosting providers (Render, Heroku) hand out "postgres://" URLs, but
    # SQLAlchemy needs the dialect + driver spelled out.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _normalize_db_url(
            os.getenv("DATABASE_URL", "sqlite:///./shortener.db")
        )
    )
    # Token bucket: each client may burst up to `capacity` link creations,
    # refilled at `refill_per_sec` tokens per second.
    rate_limit_capacity: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_CAPACITY", "10"))
    )
    rate_limit_refill_per_sec: float = field(
        default_factory=lambda: float(os.getenv("RATE_LIMIT_REFILL_PER_SEC", "0.2"))
    )
    # Behind a reverse proxy the socket peer is the proxy, so the real
    # client IP has to come from X-Forwarded-For.
    trust_proxy: bool = field(
        default_factory=lambda: os.getenv("TRUST_PROXY", "false").lower() == "true"
    )
    code_length: int = 7

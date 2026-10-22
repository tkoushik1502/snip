from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_db, make_sessionmaker
from app.models import Click, Link, utcnow
from app.ratelimit import TokenBucketLimiter
from app.schemas import DailyClicks, LinkCreate, LinkOut, LinkStats, ReferrerCount
from app.shortcode import is_valid_alias, random_code

STATIC_DIR = Path(__file__).parent / "static"
MAX_CODE_ATTEMPTS = 5
STATS_DAYS = 30


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Snip — URL shortener",
        description="Shorten URLs and track how they're clicked.",
        version="1.0.0",
    )
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(settings.database_url)
    app.state.limiter = TokenBucketLimiter(
        settings.rate_limit_capacity, settings.rate_limit_refill_per_sec
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def client_ip(request: Request) -> str:
        if settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def to_out(link: Link, request: Request) -> LinkOut:
        return LinkOut(
            code=link.code,
            short_url=f"{str(request.base_url).rstrip('/')}/{link.code}",
            target_url=link.target_url,
            created_at=link.created_at,
            expires_at=link.expires_at,
            click_count=link.click_count,
        )

    def get_link_or_404(db: Session, code: str) -> Link:
        link = db.scalar(select(Link).where(Link.code == code))
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Short link not found")
        return link

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    @app.post(
        "/api/links",
        response_model=LinkOut,
        status_code=status.HTTP_201_CREATED,
        tags=["links"],
        responses={409: {"description": "Alias already taken"}, 429: {"description": "Rate limited"}},
    )
    def create_link(body: LinkCreate, request: Request, db: Session = Depends(get_db)) -> LinkOut:
        allowed, retry_after = app.state.limiter.allow(client_ip(request))
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many links created, slow down",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        if body.alias is not None and not is_valid_alias(body.alias):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Alias must be 3-32 characters of letters, digits, '-' or '_', and not a reserved word",
            )

        expires_at = (
            utcnow() + timedelta(hours=body.expires_in_hours) if body.expires_in_hours else None
        )

        # Rather than check-then-insert (racy under concurrency), insert and let
        # the unique constraint arbitrate. On a collision, retry with a new code.
        attempts = 1 if body.alias else MAX_CODE_ATTEMPTS
        for _ in range(attempts):
            link = Link(
                code=body.alias or random_code(settings.code_length),
                target_url=str(body.url),
                expires_at=expires_at,
            )
            db.add(link)
            try:
                db.commit()
                return to_out(link, request)
            except IntegrityError:
                db.rollback()

        if body.alias:
            raise HTTPException(status.HTTP_409_CONFLICT, "That alias is already taken")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not allocate a short code, try again"
        )

    @app.get("/api/links", response_model=list[LinkOut], tags=["links"])
    def list_links(
        request: Request, limit: int = 50, db: Session = Depends(get_db)
    ) -> list[LinkOut]:
        limit = max(1, min(limit, 200))
        links = db.scalars(select(Link).order_by(Link.created_at.desc(), Link.id.desc()).limit(limit))
        return [to_out(link, request) for link in links]

    @app.get("/api/links/{code}/stats", response_model=LinkStats, tags=["links"])
    def link_stats(code: str, request: Request, db: Session = Depends(get_db)) -> LinkStats:
        link = get_link_or_404(db, code)
        today = utcnow().date()
        since = today - timedelta(days=STATS_DAYS - 1)

        day = func.date(Click.clicked_at)
        rows = db.execute(
            select(day, func.count())
            .where(Click.link_id == link.id, Click.clicked_at >= since)
            .group_by(day)
        ).all()
        # SQLite returns dates as strings, Postgres as date objects.
        counts = {str(d): n for d, n in rows}
        by_day = [
            DailyClicks(date=str(d), clicks=counts.get(str(d), 0))
            for d in (since + timedelta(days=i) for i in range(STATS_DAYS))
        ]

        referrers = db.execute(
            select(Click.referrer, func.count().label("n"))
            .where(Click.link_id == link.id)
            .group_by(Click.referrer)
            .order_by(func.count().desc())
            .limit(5)
        ).all()

        return LinkStats(
            link=to_out(link, request),
            total_clicks=link.click_count,
            clicks_by_day=by_day,
            top_referrers=[ReferrerCount(referrer=r or "direct", clicks=n) for r, n in referrers],
        )

    @app.delete("/api/links/{code}", status_code=status.HTTP_204_NO_CONTENT, tags=["links"])
    def delete_link(code: str, db: Session = Depends(get_db)) -> None:
        db.delete(get_link_or_404(db, code))
        db.commit()

    @app.get("/{code}", tags=["redirect"], status_code=status.HTTP_302_FOUND)
    def follow(code: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
        link = get_link_or_404(db, code)
        if link.is_expired():
            raise HTTPException(status.HTTP_410_GONE, "This short link has expired")

        db.add(
            Click(
                link_id=link.id,
                referrer=(request.headers.get("referer") or "")[:512] or None,
                user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            )
        )
        # Increment in SQL, not Python, so concurrent clicks can't lose updates.
        db.execute(
            update(Link).where(Link.id == link.id).values(click_count=Link.click_count + 1)
        )
        db.commit()
        # 302, not 301: browsers cache permanent redirects and would skip us,
        # so repeat clicks would never be counted.
        return RedirectResponse(link.target_url, status_code=status.HTTP_302_FOUND)

    return app


app = create_app()

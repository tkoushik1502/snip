from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    # Stored as naive UTC so SQLite and Postgres behave identically.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Unique index: every redirect is a lookup by code, and the constraint is
    # what makes concurrent collision handling safe.
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Denormalized counter so listing links doesn't need COUNT(*) over clicks.
    click_count: Mapped[int] = mapped_column(Integer, default=0)

    clicks: Mapped[list["Click"]] = relationship(
        back_populates="link", cascade="all, delete-orphan"
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and (now or utcnow()) >= self.expires_at


class Click(Base):
    __tablename__ = "clicks"
    # Stats queries filter by link and time range together.
    __table_args__ = (Index("ix_clicks_link_time", "link_id", "clicked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"))
    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    link: Mapped[Link] = relationship(back_populates="clicks")

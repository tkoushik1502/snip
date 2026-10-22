from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_sessionmaker(database_url: str) -> sessionmaker[Session]:
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            # Share one connection so every session sees the same in-memory DB.
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.sessionmaker()
    try:
        yield db
    finally:
        db.close()

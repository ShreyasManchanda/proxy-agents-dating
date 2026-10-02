"""Postgres schema (SPEC §13). Scores are derived on request, not stored."""
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer,
                        LargeBinary, String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "person"
    id: Mapped[int] = mapped_column(primary_key=True)
    linkedin_url: Mapped[str] = mapped_column(String)
    instagram_url: Mapped[str] = mapped_column(String)
    display_name: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    note: Mapped[str | None] = mapped_column(Text)  # user-visible status / failure message
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No unique constraint on the URL pair: every pasted person is a private row of their own, so that
    # deleting them removes only their data (SPEC section 12). Seeded demo people are found by URL.


class RawScrape(Base):
    __tablename__ = "raw_scrape"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String)  # li | ig | li_posts
    provider: Mapped[str] = mapped_column(String)
    payload: Mapped[dict | list | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)


class Image(Base):
    __tablename__ = "image"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    post_ref: Mapped[str | None] = mapped_column(String)
    bytes: Mapped[bytes] = mapped_column(LargeBinary)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class Observation(Base):
    __tablename__ = "observation"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    ref: Mapped[str] = mapped_column(String)
    weight: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)


class Profile(Base):
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    prompt_version: Mapped[str] = mapped_column(String)


class Date(Base):
    __tablename__ = "date"
    id: Mapped[int] = mapped_column(primary_key=True)
    a_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    b_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    scenario: Mapped[str | None] = mapped_column(String)
    first_speaker: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|failed
    model: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint("a_id < b_id"), UniqueConstraint("a_id", "b_id"))


class Verdict(Base):
    __tablename__ = "verdict"
    id: Mapped[int] = mapped_column(primary_key=True)
    date_id: Mapped[int] = mapped_column(ForeignKey("date.id", ondelete="CASCADE"), index=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    to_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    sample_idx: Mapped[int] = mapped_column(Integer)
    scores: Mapped[dict] = mapped_column(JSONB)
    second_date: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)


class Debrief(Base):
    __tablename__ = "debrief"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    ranking: Mapped[list] = mapped_column(JSONB)


class Pool(Base):
    __tablename__ = "pool"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stats: Mapped[dict | None] = mapped_column(JSONB)


class PoolMember(Base):
    __tablename__ = "pool_member"
    pool_id: Mapped[int] = mapped_column(ForeignKey("pool.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), primary_key=True)


class LlmCache(Base):
    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    response: Mapped[dict | list] = mapped_column(JSONB)
    prompt_version: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

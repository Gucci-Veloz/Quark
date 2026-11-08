"""Capa SQL (SQLAlchemy 2.x): engine, sesión y modelos de users/api_keys/profiles (specs §3.4)."""
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import DATABASE_URL


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="")  # "read,write,admin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # sha256 hex
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default", index=True)
    scopes: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_profiles_tenant_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def split_scopes(scopes: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in (scopes or "").split(",") if s.strip())


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está definida")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependencia FastAPI: una sesión por request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

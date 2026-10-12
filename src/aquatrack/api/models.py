"""Database tables."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    name: str = Field(max_length=100)
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Profile(SQLModel, table=True):
    """Answers from the profile survey, one row per user. Metric units."""

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    age: int
    height_cm: float
    weight_kg: float
    swim_level: str = Field(max_length=20)
    sessions_per_week: int
    minutes_per_day: int
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

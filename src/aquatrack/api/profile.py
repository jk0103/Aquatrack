"""The logged-in user's swimmer profile, filled in by the survey after signup."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from aquatrack.api.auth import SessionDep, current_user
from aquatrack.api.models import Profile, User

router = APIRouter(prefix="/profile", tags=["profile"])

CurrentUser = Annotated[User, Depends(current_user)]


class SwimLevel(StrEnum):
    beginner = "beginner"
    hobby = "hobby"
    masters = "masters"
    competitive = "competitive"


class ProfileIn(BaseModel):
    age: int = Field(ge=5, le=100)
    height_cm: float = Field(ge=80, le=250)
    weight_kg: float = Field(ge=15, le=250)
    swim_level: SwimLevel
    sessions_per_week: int = Field(ge=0, le=14)
    minutes_per_day: int = Field(ge=0, le=600)


class ProfileOut(ProfileIn):
    updated_at: datetime


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, session: SessionDep) -> Profile:
    profile = session.get(Profile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not filled in yet")
    return profile


@router.put("", response_model=ProfileOut)
def save_profile(body: ProfileIn, user: CurrentUser, session: SessionDep) -> Profile:
    """Create or replace the profile."""
    answers = body.model_dump(mode="json")
    profile = session.get(Profile, user.id) or Profile(user_id=user.id, **answers)
    profile.sqlmodel_update({**answers, "updated_at": datetime.now(UTC)})
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile

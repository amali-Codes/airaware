from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

LifestyleType = Literal[
    "student",
    "working professional",
    "homemaker",
    "retired",
    "other",
]

HouseholdMemberType = Literal[
    "adults",
    "children",
    "elderly people",
    "infants",
]

SensitivityType = Literal[
    "asthma",
    "allergies",
    "respiratory sensitivity",
    "none",
]

ExerciseHabitsType = Literal[
    "indoor",
    "outdoor",
    "both",
]


class UserProfile(BaseModel):
    """User profile details for personalized health and air quality guidance."""

    model_config = ConfigDict(populate_by_name=True)

    lifestyle: LifestyleType = Field(
        default="other",
        description="Daily routine or occupation: student, working professional, homemaker, retired, or other",
    )

    household_members: list[HouseholdMemberType] = Field(
        default_factory=lambda: ["adults"],
        description="Members residing in the household: adults, children, elderly people, infants",
    )

    sensitivity_considerations: Optional[SensitivityType] = Field(
        default="none",
        description="Optional health sensitivity: asthma, allergies, respiratory sensitivity, or none",
    )

    exercise_habits: ExerciseHabitsType = Field(
        default="both",
        description="Typical exercise environment: indoor, outdoor, or both",
    )

    has_air_purifier: bool = Field(
        default=False,
        description="Whether the user owns or regularly uses an indoor air purifier",
    )

    uses_mask_outdoors: bool = Field(
        default=False,
        description="Whether the user uses or wears a protective mask when outdoors",
    )

    @field_validator("lifestyle", mode="before")
    @classmethod
    def _normalize_lifestyle(cls, v: str) -> str:
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned == "working_professional":
                return "working professional"
            return cleaned
        return v

    @field_validator("household_members", mode="before")
    @classmethod
    def _normalize_household_members(cls, v):
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, str):
                    cleaned = item.strip().lower()
                    if cleaned in ("elderly", "elderly_people"):
                        cleaned = "elderly people"
                    normalized.append(cleaned)
                else:
                    normalized.append(item)
            return normalized
        return v

    @field_validator("sensitivity_considerations", mode="before")
    @classmethod
    def _normalize_sensitivity(cls, v):
        if v is None:
            return "none"
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned in ("respiratory_sensitivity", "respiratory"):
                return "respiratory sensitivity"
            return cleaned
        if isinstance(v, list):
            return v[0] if v else "none"
        return v

    @field_validator("exercise_habits", mode="before")
    @classmethod
    def _normalize_exercise_habits(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @property
    def sensitivity(self) -> Optional[SensitivityType]:
        return self.sensitivity_considerations

    @property
    def mask_outdoors(self) -> bool:
        return self.uses_mask_outdoors


from pydantic import BaseModel, Field


class AIRecommendations(BaseModel):
    """AI-generated practical air quality recommendations."""

    outdoor_activity: str = Field(
        ...,
        description="Advice about outdoor activities based on current air quality",
    )

    sensitive_groups: str = Field(
        ...,
        description="Precautions for children, older adults, and people with respiratory conditions",
    )

    protection_tips: list[str] = Field(
        ...,
        description="Practical steps to reduce exposure to air pollution",
        min_length=1,
        max_length=5,
    )

    summary: str = Field(
        ...,
        description="A short, easy-to-understand recommendation summary",
    )

    source: str = Field(
        default="gemini",
        description="Whether recommendations came from Gemini or fallback rules",
    )

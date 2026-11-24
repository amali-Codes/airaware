import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from backend.schemas.recommendations import AIRecommendations
from backend.schemas.user_profile import UserProfile
from backend.services.open_meteo import (
    OpenMeteoService,
    CityNotFoundError,
    OpenMeteoAPIError,
    OpenMeteoNetworkError,
)
from backend.services.recommendation_service import RecommendationService

app = FastAPI(
    title="AirAware API",
    description="AI-powered urban air quality assistant",
    version="1.0.0",
)

# Allow the React frontend to communicate with FastAPI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RecommendationsRequest(BaseModel):
    """Request payload for personalized recommendations with UserProfile."""

    city: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City name to fetch recommendations for",
    )
    profile: Optional[UserProfile] = Field(
        default_factory=UserProfile,
        description="Optional user wellness and lifestyle profile",
    )


async def _fetch_recommendations_for_city(
    city: str,
    user_profile: Optional[UserProfile] = None,
) -> AIRecommendations:
    """Internal helper to retrieve air quality and generate personalized recommendations."""
    cleaned_city = city.strip()
    if not cleaned_city:
        raise HTTPException(
            status_code=422,
            detail="City name cannot be empty.",
        )

    try:
        async with OpenMeteoService() as service:
            air_quality = await service.get_air_quality_by_city(cleaned_city)

        aqi_info = air_quality.current.us_aqi

        if aqi_info.value is None:
            raise HTTPException(
                status_code=422,
                detail="AQI data is unavailable for this city.",
            )

        rec_service = RecommendationService()

        recommendations = await asyncio.to_thread(
            rec_service.generate_recommendations,
            city=air_quality.location.name,
            aqi=aqi_info.value,
            category=aqi_info.category,
            pollutants=air_quality.current.pollutants.model_dump(),
            user_profile=user_profile,
        )

        return recommendations

    except CityNotFoundError:
        raise HTTPException(status_code=404, detail="City not found.")

    except OpenMeteoNetworkError:
        raise HTTPException(
            status_code=503,
            detail="Unable to connect to the air quality service.",
        )

    except OpenMeteoAPIError:
        raise HTTPException(
            status_code=502,
            detail="Air quality service returned an error.",
        )


@app.get("/")
def home():
    return {
        "message": "Welcome to AirAware!",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/health")
def api_health_check():
    return {
        "status": "healthy",
        "service": "AirAware API",
    }


@app.get("/api/air-quality")
async def get_air_quality(
    city: str = Query(
        ...,
        min_length=1,
        max_length=100,
        description="City name to search for",
    )
):
    try:
        async with OpenMeteoService() as service:
            result = await service.get_air_quality_by_city(city.strip())

        return result

    except CityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except OpenMeteoNetworkError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except OpenMeteoAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@app.get("/api/recommendations", response_model=AIRecommendations)
async def get_recommendations(
    city: str = Query(..., min_length=1, max_length=100, description="Target city name"),
    lifestyle: Optional[str] = None,
    exercise_habits: Optional[str] = None,
    sensitivity: Optional[str] = None,
    has_air_purifier: Optional[bool] = None,
    uses_mask_outdoors: Optional[bool] = None,
):
    profile_kwargs = {}
    if lifestyle is not None:
        profile_kwargs["lifestyle"] = lifestyle
    if exercise_habits is not None:
        profile_kwargs["exercise_habits"] = exercise_habits
    if sensitivity is not None:
        profile_kwargs["sensitivity_considerations"] = sensitivity
    if has_air_purifier is not None:
        profile_kwargs["has_air_purifier"] = has_air_purifier
    if uses_mask_outdoors is not None:
        profile_kwargs["uses_mask_outdoors"] = uses_mask_outdoors

    try:
        user_profile = UserProfile(**profile_kwargs) if profile_kwargs else UserProfile()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    return await _fetch_recommendations_for_city(city, user_profile)


@app.post("/api/recommendations", response_model=AIRecommendations)
async def create_recommendations(
    payload: RecommendationsRequest,
):
    user_profile = payload.profile or UserProfile()
    return await _fetch_recommendations_for_city(payload.city, user_profile)

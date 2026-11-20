import asyncio

from backend.schemas.recommendations import AIRecommendations
from backend.services.recommendation_service import RecommendationService
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.services.open_meteo import (
    OpenMeteoService,
    CityNotFoundError,
    OpenMeteoAPIError,
    OpenMeteoNetworkError,
)

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
    city: str = Query(..., min_length=1, max_length=100)
):
    try:
        # Get the latest air quality data
        air_quality = await OpenMeteoService().get_air_quality_by_city(
            city.strip()
        )

        aqi_info = air_quality.current.us_aqi

        if aqi_info.value is None:
            raise HTTPException(
                status_code=422,
                detail="AQI data is unavailable for this city.",
            )

        # Generate recommendations using Gemini
        service = RecommendationService()

        recommendations = await asyncio.to_thread(
            service.generate_recommendations,
            city=air_quality.location.name,
            aqi=aqi_info.value,
            category=aqi_info.category,
            pollutants=air_quality.current.pollutants.model_dump(),
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
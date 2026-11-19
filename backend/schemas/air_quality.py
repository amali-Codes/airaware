
from typing import Dict, Optional
from pydantic import BaseModel, Field


def calculate_aqi_category(aqi: Optional[int]) -> tuple[str, str, str]:
    """
    Categorize a US AQI value into health category,
    health description, and UI color.
    """

    if aqi is None:
        return (
            "Unknown",
            "No air quality index data is available for this location.",
            "#94a3b8",
        )

    if aqi < 0:
        return (
            "Invalid",
            "Invalid AQI reading provided.",
            "#94a3b8",
        )
    elif aqi <= 50:
        return (
            "Good",
            "Air quality is satisfactory, and air pollution poses little or no risk.",
            "#10b981",
        )
    elif aqi <= 100:
        return (
            "Moderate",
            "Air quality is acceptable; however, sensitive people may experience minor respiratory symptoms.",
            "#eab308",
        )
    elif aqi <= 150:
        return (
            "Unhealthy for Sensitive Groups",
            "Members of sensitive groups may experience health effects. The general public is less likely to be affected.",
            "#f97316",
        )
    elif aqi <= 200:
        return (
            "Unhealthy",
            "Everyone may begin to experience health effects; members of sensitive groups may experience more serious effects.",
            "#ef4444",
        )
    elif aqi <= 300:
        return (
            "Very Unhealthy",
            "Health alert: The risk of health effects is increased for everyone.",
            "#8b5cf6",
        )
    else:
        return (
            "Hazardous",
            "Health warning of emergency conditions: The entire population is likely to be affected.",
            "#7f1d1d",
        )


class Location(BaseModel):
    """Geographic location details resolved from city search."""

    name: str = Field(..., description="Name of the city or locality")
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    country: Optional[str] = Field(default=None, description="Country name")
    country_code: Optional[str] = Field(default=None, description="ISO two-letter country code")
    admin1: Optional[str] = Field(default=None, description="State, province, or primary administrative division")
    timezone: Optional[str] = Field(default=None, description="Local timezone string")


class AQIInfo(BaseModel):
    """Air Quality Index reading and health categorization."""

    value: Optional[int] = Field(default=None, description="Numeric AQI value")
    category: str = Field(..., description="US EPA category name")
    description: str = Field(..., description="Human-friendly health impact guidance")
    color: str = Field(..., description="Suggested Hex color code for UI rendering")


class PollutantValues(BaseModel):
    """Concentration levels for major atmospheric pollutants."""

    pm2_5: Optional[float] = Field(default=None, description="Fine particulate matter PM2.5 (µg/m³)")
    pm10: Optional[float] = Field(default=None, description="Coarse particulate matter PM10 (µg/m³)")
    nitrogen_dioxide: Optional[float] = Field(default=None, description="Nitrogen dioxide NO2 (µg/m³)")
    ozone: Optional[float] = Field(default=None, description="Ozone O3 (µg/m³)")
    sulphur_dioxide: Optional[float] = Field(default=None, description="Sulphur dioxide SO2 (µg/m³)")
    carbon_monoxide: Optional[float] = Field(default=None, description="Carbon monoxide CO (µg/m³)")


class AirQualityCurrent(BaseModel):
    """Snapshot of current atmospheric measurements."""

    timestamp: str = Field(..., description="ISO 8601 observation timestamp")
    us_aqi: AQIInfo = Field(..., description="US EPA Air Quality Index details")
    european_aqi: Optional[int] = Field(default=None, description="European Air Quality Index value")
    pollutants: PollutantValues = Field(default_factory=PollutantValues)
    units: Dict[str, str] = Field(default_factory=dict)


class AirQualityResponse(BaseModel):
    """Standardized API response payload combining location, readings, and advice."""

    location: Location = Field(..., description="Location information")
    current: AirQualityCurrent = Field(..., description="Current air quality observations")
    summary: str = Field(..., description="Digestible overview summary")

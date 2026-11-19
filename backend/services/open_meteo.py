
from typing import Any, Dict, Optional
from math import isfinite

import httpx
from pydantic import ValidationError

from backend.schemas.air_quality import (
    AirQualityCurrent,
    AirQualityResponse,
    AQIInfo,
    Location,
    PollutantValues,
    calculate_aqi_category,
)


class OpenMeteoError(Exception):
    """Base exception for Open-Meteo service errors."""
    pass


class CityNotFoundError(OpenMeteoError):
    """Raised when a city cannot be found."""
    pass


class OpenMeteoAPIError(OpenMeteoError):
    """Raised when the API returns an error or invalid data."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class OpenMeteoNetworkError(OpenMeteoError):
    """Raised when a network error or timeout occurs."""
    pass


class OpenMeteoService:
    """Client for Open-Meteo Geocoding and Air Quality APIs."""

    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 10.0,
    ):
        self._client = client
        self._owns_client = client is None
        self.timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        """Get an active HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True

        return self._client

    async def close(self) -> None:
        """Close the client if this service created it."""
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @staticmethod
    def _parse_json(response: httpx.Response) -> Dict[str, Any]:
        """Parse and validate an API JSON response."""
        try:
            data = response.json()
        except ValueError as exc:
            raise OpenMeteoAPIError("Open-Meteo returned invalid JSON.") from exc

        if not isinstance(data, dict):
            raise OpenMeteoAPIError("Open-Meteo returned an unexpected response format.")

        return data

    @staticmethod
    def _parse_aqi(value: Any) -> Optional[int]:
        """Safely convert an AQI value into an integer."""
        if value is None:
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OpenMeteoAPIError("Open-Meteo returned a non-numeric AQI value.")

        if not isfinite(value):
            raise OpenMeteoAPIError("Open-Meteo returned an invalid AQI value.")

        return int(round(value))

    async def get_coordinates(self, city_name: str) -> Location:
        """Find a city and retrieve its geographical coordinates."""

        cleaned_city = city_name.strip() if city_name else ""

        if not cleaned_city:
            raise CityNotFoundError("City name cannot be empty.")

        client = await self._get_client()

        params = {
            "name": cleaned_city,
            "count": 1,
            "language": "en",
            "format": "json",
        }

        try:
            response = await client.get(self.GEOCODING_URL, params=params)
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise OpenMeteoNetworkError(
                f"Timeout while searching for {cleaned_city}."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise OpenMeteoAPIError(
                f"Geocoding API returned status {exc.response.status_code}.",
                status_code=exc.response.status_code,
            ) from exc

        except httpx.RequestError as exc:
            raise OpenMeteoNetworkError(
                "Network error while connecting to Geocoding API."
            ) from exc

        data = self._parse_json(response)
        results = data.get("results")

        if not isinstance(results, list) or not results:
            raise CityNotFoundError(
                f"City '{cleaned_city}' was not found."
            )

        first_match = results[0]

        if not isinstance(first_match, dict):
            raise OpenMeteoAPIError("Invalid city information received.")

        try:
            return Location(
                name=first_match.get("name", cleaned_city),
                latitude=first_match["latitude"],
                longitude=first_match["longitude"],
                country=first_match.get("country"),
                country_code=first_match.get("country_code"),
                admin1=first_match.get("admin1"),
                timezone=first_match.get("timezone"),
            )
        except (KeyError, ValidationError) as exc:
            raise OpenMeteoAPIError(
                "Geocoding API returned incomplete or invalid location data."
            ) from exc

    async def get_air_quality(
        self,
        latitude: float,
        longitude: float,
    ) -> AirQualityCurrent:
        """Fetch current AQI and pollutant readings."""

        client = await self._get_client()

        current_vars = [
            "european_aqi",
            "us_aqi",
            "pm10",
            "pm2_5",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "ozone",
        ]

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(current_vars),
        }

        try:
            response = await client.get(self.AIR_QUALITY_URL, params=params)
            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise OpenMeteoNetworkError(
                "Timeout while fetching air quality readings."
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise OpenMeteoAPIError(
                f"Air Quality API returned status {exc.response.status_code}.",
                status_code=exc.response.status_code,
            ) from exc

        except httpx.RequestError as exc:
            raise OpenMeteoNetworkError(
                "Network error while connecting to Air Quality API."
            ) from exc

        data = self._parse_json(response)

        current_data = data.get("current")
        units_data = data.get("current_units", {})

        if not isinstance(current_data, dict) or not current_data:
            raise OpenMeteoAPIError(
                "Air Quality API did not return current readings."
            )

        if not isinstance(units_data, dict):
            raise OpenMeteoAPIError("Invalid measurement units received.")

        timestamp = current_data.get("time")

        if not isinstance(timestamp, str) or not timestamp:
            raise OpenMeteoAPIError("Air Quality API did not return a valid timestamp.")

        us_aqi_val = self._parse_aqi(current_data.get("us_aqi"))
        eu_val = self._parse_aqi(current_data.get("european_aqi"))

        category, description, color = calculate_aqi_category(us_aqi_val)

        aqi_info = AQIInfo(
            value=us_aqi_val,
            category=category,
            description=description,
            color=color,
        )

        try:
            pollutants = PollutantValues(
                pm2_5=current_data.get("pm2_5"),
                pm10=current_data.get("pm10"),
                nitrogen_dioxide=current_data.get("nitrogen_dioxide"),
                ozone=current_data.get("ozone"),
                sulphur_dioxide=current_data.get("sulphur_dioxide"),
                carbon_monoxide=current_data.get("carbon_monoxide"),
            )

            clean_units = {
                key: str(value)
                for key, value in units_data.items()
                if key not in ("time", "interval")
            }

            return AirQualityCurrent(
                timestamp=timestamp,
                us_aqi=aqi_info,
                european_aqi=eu_val,
                pollutants=pollutants,
                units=clean_units,
            )

        except ValidationError as exc:
            raise OpenMeteoAPIError(
                "Air Quality API returned invalid pollutant data."
            ) from exc

    async def get_air_quality_by_city(
        self,
        city_name: str,
    ) -> AirQualityResponse:
        """Retrieve a complete air quality response for a city."""

        location = await self.get_coordinates(city_name)

        air_quality = await self.get_air_quality(
            location.latitude,
            location.longitude,
        )

        aqi_display = (
            str(air_quality.us_aqi.value)
            if air_quality.us_aqi.value is not None
            else "N/A"
        )

        summary = (
            f"Current air quality in {location.name} is "
            f"{air_quality.us_aqi.category} "
            f"(US AQI: {aqi_display}). "
            f"{air_quality.us_aqi.description}"
        )

        return AirQualityResponse(
            location=location,
            current=air_quality,
            summary=summary,
        )

import functools
import unittest
from unittest.mock import AsyncMock, patch
import httpx

from backend.schemas.air_quality import (
    AirQualityCurrent,
    AirQualityResponse,
    AQIInfo,
    Location,
    PollutantValues,
    calculate_aqi_category,
)
from backend.services.open_meteo import (
    CityNotFoundError,
    OpenMeteoAPIError,
    OpenMeteoNetworkError,
    OpenMeteoService,
)


def run_async(coro):
    """
    Lightweight coroutine runner that drives an async function to completion.
    Avoids initializing OS-level socketpairs/pipes that are restricted in sandboxed
    environments, enabling fast, isolated unit testing of async service logic.
    """
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


def async_test(coro_fn):
    """Decorator to run an async test method synchronously using run_async."""
    @functools.wraps(coro_fn)
    def wrapper(*args, **kwargs):
        return run_async(coro_fn(*args, **kwargs))
    return wrapper


class TestAQICalculation(unittest.TestCase):
    """Unit tests for the calculate_aqi_category utility function."""

    def test_aqi_none(self):
        cat, desc, color = calculate_aqi_category(None)
        self.assertEqual(cat, "Unknown")
        self.assertEqual(color, "#94a3b8")

    def test_aqi_negative(self):
        cat, desc, color = calculate_aqi_category(-10)
        self.assertEqual(cat, "Invalid")

    def test_aqi_good(self):
        for val in (0, 25, 50):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Good")
            self.assertEqual(color, "#10b981")

    def test_aqi_moderate(self):
        for val in (51, 75, 100):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Moderate")
            self.assertEqual(color, "#eab308")

    def test_aqi_unhealthy_sensitive(self):
        for val in (101, 125, 150):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Unhealthy for Sensitive Groups")
            self.assertEqual(color, "#f97316")

    def test_aqi_unhealthy(self):
        for val in (151, 175, 200):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Unhealthy")
            self.assertEqual(color, "#ef4444")

    def test_aqi_very_unhealthy(self):
        for val in (201, 250, 300):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Very Unhealthy")
            self.assertEqual(color, "#8b5cf6")

    def test_aqi_hazardous(self):
        for val in (301, 450, 500):
            cat, desc, color = calculate_aqi_category(val)
            self.assertEqual(cat, "Hazardous")
            self.assertEqual(color, "#7f1d1d")


class TestSchemas(unittest.TestCase):
    """Unit tests for Pydantic data models."""

    def test_location_creation_minimal(self):
        loc = Location(name="Bengaluru", latitude=12.9716, longitude=77.5946)
        self.assertEqual(loc.name, "Bengaluru")
        self.assertEqual(loc.latitude, 12.9716)
        self.assertEqual(loc.longitude, 77.5946)
        self.assertIsNone(loc.country)
        self.assertIsNone(loc.timezone)

    def test_location_creation_full(self):
        loc = Location(
            name="Bengaluru",
            latitude=12.9716,
            longitude=77.5946,
            country="India",
            country_code="IN",
            admin1="Karnataka",
            timezone="Asia/Kolkata",
        )
        self.assertEqual(loc.country, "India")
        self.assertEqual(loc.country_code, "IN")
        self.assertEqual(loc.admin1, "Karnataka")

    def test_air_quality_response_serialization(self):
        loc = Location(name="Delhi", latitude=28.6139, longitude=77.2090)
        aqi_info = AQIInfo(
            value=165,
            category="Unhealthy",
            description="Everyone may begin to experience health effects.",
            color="#ef4444",
        )
        pollutants = PollutantValues(pm2_5=85.4, pm10=140.2)
        current = AirQualityCurrent(
            timestamp="2026-11-19T05:00",
            us_aqi=aqi_info,
            pollutants=pollutants,
            units={"pm2_5": "μg/m³", "pm10": "μg/m³"},
        )
        response = AirQualityResponse(
            location=loc,
            current=current,
            summary="Air quality in Delhi is Unhealthy.",
        )

        dump = response.model_dump()
        self.assertEqual(dump["location"]["name"], "Delhi")
        self.assertEqual(dump["current"]["us_aqi"]["value"], 165)
        self.assertEqual(dump["current"]["pollutants"]["pm2_5"], 85.4)
        self.assertIsNone(dump["current"]["pollutants"]["ozone"])


class TestOpenMeteoServiceGeocoding(unittest.TestCase):
    """Mocked unit tests for OpenMeteoService geocoding operations."""

    @async_test
    async def test_get_coordinates_success(self):
        fake_payload = {
            "results": [
                {
                    "id": 1277333,
                    "name": "Bengaluru",
                    "latitude": 12.97194,
                    "longitude": 77.59369,
                    "country": "India",
                    "country_code": "IN",
                    "admin1": "Karnataka",
                    "timezone": "Asia/Kolkata",
                }
            ]
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=200,
            json=fake_payload,
            request=httpx.Request("GET", "https://geocoding-api.open-meteo.com/v1/search"),
        )

        service = OpenMeteoService(client=mock_client)
        location = await service.get_coordinates("Bengaluru")

        self.assertEqual(location.name, "Bengaluru")
        self.assertAlmostEqual(location.latitude, 12.97194)
        self.assertAlmostEqual(location.longitude, 77.59369)
        self.assertEqual(location.country, "India")
        self.assertEqual(location.country_code, "IN")
        self.assertEqual(location.admin1, "Karnataka")

    @async_test
    async def test_get_coordinates_city_not_found_empty_results(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=200,
            json={"results": []},
            request=httpx.Request("GET", "https://geocoding-api.open-meteo.com/v1/search"),
        )

        service = OpenMeteoService(client=mock_client)
        with self.assertRaises(CityNotFoundError):
            await service.get_coordinates("NonExistentCityXYZ")

    @async_test
    async def test_get_coordinates_empty_input(self):
        service = OpenMeteoService()
        with self.assertRaises(CityNotFoundError):
            await service.get_coordinates("   ")

    @async_test
    async def test_get_coordinates_http_500_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("GET", "https://geocoding-api.open-meteo.com/v1/search"),
        )

        service = OpenMeteoService(client=mock_client)
        with self.assertRaises(OpenMeteoAPIError) as ctx:
            await service.get_coordinates("Bengaluru")
        self.assertEqual(ctx.exception.status_code, 500)

    @async_test
    async def test_get_coordinates_timeout_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

        service = OpenMeteoService(client=mock_client)
        with self.assertRaises(OpenMeteoNetworkError):
            await service.get_coordinates("Bengaluru")

    @async_test
    async def test_get_coordinates_network_request_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.side_effect = httpx.RequestError("Network unreachable")

        service = OpenMeteoService(client=mock_client)
        with self.assertRaises(OpenMeteoNetworkError):
            await service.get_coordinates("Bengaluru")


class TestOpenMeteoServiceAirQuality(unittest.TestCase):
    """Mocked unit tests for OpenMeteoService air quality fetch."""

    @async_test
    async def test_get_air_quality_success(self):
        fake_payload = {
            "latitude": 12.97,
            "longitude": 77.59,
            "current_units": {
                "time": "iso8601",
                "interval": "seconds",
                "european_aqi": "AQI",
                "us_aqi": "AQI",
                "pm10": "μg/m³",
                "pm2_5": "μg/m³",
                "carbon_monoxide": "μg/m³",
                "nitrogen_dioxide": "μg/m³",
                "sulphur_dioxide": "μg/m³",
                "ozone": "μg/m³",
            },
            "current": {
                "time": "2026-11-19T05:00",
                "interval": 3600,
                "european_aqi": 52.0,
                "us_aqi": 78.0,
                "pm10": 42.1,
                "pm2_5": 25.3,
                "carbon_monoxide": 250.0,
                "nitrogen_dioxide": 14.8,
                "sulphur_dioxide": 3.9,
                "ozone": 35.2,
            },
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=200,
            json=fake_payload,
            request=httpx.Request("GET", "https://air-quality-api.open-meteo.com/v1/air-quality"),
        )

        service = OpenMeteoService(client=mock_client)
        air_quality = await service.get_air_quality(12.97, 77.59)

        self.assertEqual(air_quality.timestamp, "2026-11-19T05:00")
        self.assertEqual(air_quality.us_aqi.value, 78)
        self.assertEqual(air_quality.us_aqi.category, "Moderate")
        self.assertEqual(air_quality.us_aqi.color, "#eab308")
        self.assertEqual(air_quality.european_aqi, 52)
        self.assertEqual(air_quality.pollutants.pm2_5, 25.3)
        self.assertEqual(air_quality.pollutants.pm10, 42.1)
        self.assertEqual(air_quality.pollutants.nitrogen_dioxide, 14.8)
        self.assertEqual(air_quality.pollutants.ozone, 35.2)
        self.assertEqual(air_quality.pollutants.sulphur_dioxide, 3.9)
        self.assertEqual(air_quality.pollutants.carbon_monoxide, 250.0)

        # Ensure "time" and "interval" were filtered out from units
        self.assertNotIn("time", air_quality.units)
        self.assertNotIn("interval", air_quality.units)
        self.assertEqual(air_quality.units["pm2_5"], "μg/m³")

    @async_test
    async def test_get_air_quality_with_null_pollutants(self):
        fake_payload = {
            "current_units": {"pm2_5": "μg/m³"},
            "current": {
                "time": "2026-11-19T05:00",
                "us_aqi": None,
                "european_aqi": None,
                "pm2_5": 12.0,
                "pm10": None,
                "ozone": None,
            },
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=200,
            json=fake_payload,
            request=httpx.Request("GET", "https://air-quality-api.open-meteo.com/v1/air-quality"),
        )

        service = OpenMeteoService(client=mock_client)
        air_quality = await service.get_air_quality(0.0, 0.0)

        self.assertIsNone(air_quality.us_aqi.value)
        self.assertEqual(air_quality.us_aqi.category, "Unknown")
        self.assertEqual(air_quality.pollutants.pm2_5, 12.0)
        self.assertIsNone(air_quality.pollutants.pm10)

    @async_test
    async def test_get_air_quality_api_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.get.return_value = httpx.Response(
            status_code=400,
            text="Bad Request: invalid coordinates",
            request=httpx.Request("GET", "https://air-quality-api.open-meteo.com/v1/air-quality"),
        )

        service = OpenMeteoService(client=mock_client)
        with self.assertRaises(OpenMeteoAPIError) as ctx:
            await service.get_air_quality(999.0, 999.0)
        self.assertEqual(ctx.exception.status_code, 400)


class TestOpenMeteoServiceEndToEnd(unittest.TestCase):
    """Mocked end-to-end tests for get_air_quality_by_city orchestration."""

    @async_test
    async def test_get_air_quality_by_city_success(self):
        service = OpenMeteoService()

        fake_location = Location(
            name="Bengaluru",
            latitude=12.9716,
            longitude=77.5946,
            country="India",
        )
        fake_current = AirQualityCurrent(
            timestamp="2026-11-19T05:00",
            us_aqi=AQIInfo(
                value=42,
                category="Good",
                description="Air quality is satisfactory.",
                color="#10b981",
            ),
            pollutants=PollutantValues(pm2_5=9.8, pm10=22.4),
            units={"pm2_5": "μg/m³"},
        )

        with patch.object(service, "get_coordinates", new_callable=AsyncMock) as mock_coords, \
             patch.object(service, "get_air_quality", new_callable=AsyncMock) as mock_aq:
            mock_coords.return_value = fake_location
            mock_aq.return_value = fake_current

            response = await service.get_air_quality_by_city("Bengaluru")

            mock_coords.assert_called_once_with("Bengaluru")
            mock_aq.assert_called_once_with(12.9716, 77.5946)

            self.assertEqual(response.location.name, "Bengaluru")
            self.assertEqual(response.current.us_aqi.value, 42)
            self.assertEqual(response.current.us_aqi.category, "Good")
            self.assertIn("Bengaluru", response.summary)
            self.assertIn("Good", response.summary)

    @async_test
    async def test_get_air_quality_by_city_not_found(self):
        service = OpenMeteoService()

        with patch.object(service, "get_coordinates", new_callable=AsyncMock) as mock_coords:
            mock_coords.side_effect = CityNotFoundError("City 'Atlantis' was not found.")

            with self.assertRaises(CityNotFoundError):
                await service.get_air_quality_by_city("Atlantis")

    @async_test
    async def test_service_context_manager(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()

        # Context manager lifecycle with caller-provided client
        async with OpenMeteoService(client=mock_client) as service:
            client = await service._get_client()
            self.assertEqual(client, mock_client)
            self.assertFalse(service._owns_client)
        mock_client.aclose.assert_not_awaited()

        # Owned client lifecycle
        owned_service = OpenMeteoService()
        owned_service._client = mock_client
        owned_service._owns_client = True
        await owned_service.close()
        mock_client.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

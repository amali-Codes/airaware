
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from backend.schemas.recommendations import AIRecommendations


load_dotenv()


class RecommendationService:
    """Generate recommendations using Gemini with a rule-based fallback."""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model = "gemini-3.6-flash"

    def _fallback_recommendations(
        self, aqi: int
    ) -> AIRecommendations:
        """Provide recommendations based on US AQI levels."""

        if aqi <= 50:
            return AIRecommendations(
                outdoor_activity="Air quality is good. Enjoy outdoor activities as usual.",
                sensitive_groups="No special precautions are generally needed.",
                protection_tips=[
                    "Continue your normal outdoor routine.",
                    "Stay hydrated throughout the day.",
                ],
                summary="Air quality is good. It is a suitable time to enjoy the outdoors.",
                source="fallback",
            )

        if aqi <= 100:
            return AIRecommendations(
                outdoor_activity="Most people can enjoy outdoor activities. Consider reducing prolonged intense exercise if you are unusually sensitive.",
                sensitive_groups="Unusually sensitive people should monitor how they feel outdoors.",
                protection_tips=[
                    "Pay attention to any breathing discomfort.",
                    "Reduce prolonged outdoor exertion if you feel unwell.",
                ],
                summary="Air quality is acceptable, but unusually sensitive people should take care.",
                source="fallback",
            )

        if aqi <= 150:
            return AIRecommendations(
                outdoor_activity="Consider reducing prolonged or intense outdoor exercise.",
                sensitive_groups="Children, older adults, and people with respiratory or heart conditions should limit prolonged outdoor exertion.",
                protection_tips=[
                    "Reduce strenuous outdoor exercise.",
                    "Keep windows closed when outdoor air quality is poor.",
                    "Consider a well-fitting particulate respirator outdoors if needed.",
                ],
                summary="Air quality may affect sensitive groups. Take precautions when outdoors.",
                source="fallback",
            )

        if aqi <= 200:
            return AIRecommendations(
                outdoor_activity="Avoid prolonged or strenuous outdoor activities.",
                sensitive_groups="Sensitive groups should avoid outdoor physical activity where possible.",
                protection_tips=[
                    "Move exercise indoors.",
                    "Keep windows and doors closed when outdoor air is polluted.",
                    "Use an appropriately sized air purifier indoors if available.",
                    "Consider a well-fitting particulate respirator if going outside.",
                ],
                summary="Air quality is unhealthy. Reduce outdoor exposure.",
                source="fallback",
            )

        if aqi <= 300:
            return AIRecommendations(
                outdoor_activity="Avoid outdoor physical activity.",
                sensitive_groups="Everyone should reduce outdoor exposure. Sensitive groups should remain indoors where possible.",
                protection_tips=[
                    "Stay indoors and keep windows closed.",
                    "Avoid outdoor exercise.",
                    "Use indoor air filtration if available.",
                    "Wear a well-fitting particulate respirator if going outside is unavoidable.",
                ],
                summary="Air quality is very unhealthy. Take steps to protect yourself.",
                source="fallback",
            )

        return AIRecommendations(
            outdoor_activity="Avoid outdoor activities and remain indoors.",
            sensitive_groups="Everyone should avoid outdoor exposure as much as possible.",
            protection_tips=[
                "Stay indoors with windows and doors closed.",
                "Use effective indoor air filtration if available.",
                "Avoid outdoor exercise and strenuous activity.",
                "Follow local public health advisories.",
            ],
            summary="Air quality is hazardous. Minimize exposure and follow health advisories.",
            source="fallback",
        )

    def generate_recommendations(
        self,
        city: str,
        aqi: int,
        category: str,
        pollutants: dict,
    ) -> AIRecommendations:

        if self.client is None:
            return self._fallback_recommendations(aqi)

        prompt = f"""
        You are an air quality health assistant for AirAware.

        Use ONLY the following actual air quality information.

        City: {city}
        US AQI: {aqi}
        AQI Category: {category}
        Pollutant Readings: {pollutants}

        Provide:
        1. Outdoor activity advice.
        2. Precautions for sensitive groups.
        3. Between 1 and 5 practical protection tips.
        4. A short summary.

        Do not invent measurements or make unsupported medical claims.
        Keep the language simple and concise.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIRecommendations,
                ),
            )

            return AIRecommendations.model_validate_json(response.text)

        except (APIError, ValidationError, ValueError, TypeError):
            return self._fallback_recommendations(aqi)


import json
import os

from dotenv import load_dotenv
from google import genai

from backend.schemas.air_quality import AirQualityResponse
from backend.schemas.recommendations import AIRecommendations


load_dotenv()


def generate_recommendations(
    air_quality: AirQualityResponse,
) -> AIRecommendations:
    """Generate practical recommendations using Gemini and real AQI data."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=api_key)

    air_quality_data = air_quality.model_dump_json(indent=2)

    prompt = f"""
You are an air quality information assistant for AirAware.

Use only the air quality measurements provided below.

Generate practical, clear recommendations for the user.

Rules:
- Base all advice on the supplied AQI and pollutant readings.
- Never invent measurements or air quality values.
- Do not diagnose medical conditions.
- Give sensible precautions for children, older adults,
  and people with respiratory conditions.
- Keep the language simple and concise.
- Return valid JSON with exactly these fields:
  outdoor_activity, sensitive_groups, protection_tips, summary.
- protection_tips must be a list of 1 to 5 short tips.

Air quality data:
{air_quality_data}
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result = json.loads(response.text)

    return AIRecommendations(
        **result,
        source="gemini",
    )

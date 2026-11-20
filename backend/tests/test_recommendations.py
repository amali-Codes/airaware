
from backend.services.recommendation_service import RecommendationService


def test_fallback_recommendations_for_moderate_aqi():
    """Check that moderate AQI produces valid fallback recommendations."""

    service = RecommendationService()

    result = service._fallback_recommendations(aqi=125)

    assert result.source == "fallback"
    assert result.outdoor_activity
    assert result.sensitive_groups
    assert len(result.protection_tips) >= 1
    assert result.summary


def test_fallback_recommendations_for_good_aqi():
    """Check that good AQI produces suitable recommendations."""

    service = RecommendationService()

    result = service._fallback_recommendations(aqi=35)

    assert result.source == "fallback"
    assert "good" in result.summary.lower()
    assert len(result.protection_tips) >= 1

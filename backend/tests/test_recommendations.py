import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.main import (
    RecommendationsRequest,
    create_recommendations,
    get_recommendations,
)
from backend.schemas.air_quality import (
    AirQualityCurrent,
    AirQualityResponse,
    AQIInfo,
    Location,
    PollutantValues,
)
from backend.schemas.user_profile import UserProfile
from backend.services.open_meteo import (
    CityNotFoundError,
    OpenMeteoAPIError,
    OpenMeteoNetworkError,
)
from backend.services.recommendation_service import RecommendationService


def run_async(coro):
    """
    Run an async coroutine for synchronous tests.
    Executes asyncio.to_thread synchronously in the test environment so no
    OS loopback sockets or event loop thread pools are required.
    """
    async def _mock_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("backend.main.asyncio.to_thread", new=_mock_to_thread):
        try:
            while True:
                coro.send(None)
        except StopIteration as e:
            return e.value


# ==============================================================================
# Preserved Existing Baseline Tests
# ==============================================================================


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


# ==============================================================================
# Personalized Fallback Tests
# ==============================================================================


def test_fallback_personalized_for_asthma():
    """Check that fallback gives practical, non-diagnostic guidance for asthma."""
    service = RecommendationService()
    profile = UserProfile(sensitivity_considerations="asthma")

    result = service._fallback_recommendations(aqi=130, user_profile=profile)

    assert result.source == "fallback"
    combined_text = (
        result.sensitive_groups + " " + " ".join(result.protection_tips)
    ).lower()
    assert "asthma" in combined_text


def test_fallback_personalized_for_vulnerable_household():
    """Check that fallback accounts for infants, children, and elderly members."""
    service = RecommendationService()
    profile = UserProfile(
        household_members=["infants", "elderly people", "children"]
    )

    result = service._fallback_recommendations(aqi=140, user_profile=profile)

    sensitive_text = result.sensitive_groups.lower()
    assert (
        "infants" in sensitive_text
        or "older adults" in sensitive_text
        or "children" in sensitive_text
    )


def test_fallback_personalized_for_exercise_habits():
    """Check that outdoor workout advice changes based on exercise habits."""
    service = RecommendationService()

    outdoor_profile = UserProfile(exercise_habits="outdoor")
    indoor_profile = UserProfile(exercise_habits="indoor")

    outdoor_result = service._fallback_recommendations(
        aqi=135, user_profile=outdoor_profile
    )
    indoor_result = service._fallback_recommendations(
        aqi=135, user_profile=indoor_profile
    )

    # Outdoor exerciser should be advised to reschedule or move inside
    assert "indoor" in outdoor_result.outdoor_activity.lower() or "morning" in outdoor_result.outdoor_activity.lower()
    assert "indoor" in indoor_result.outdoor_activity.lower()


def test_fallback_personalized_for_purifier_and_mask():
    """Check that air purifier ownership and outdoor mask usage influence tips."""
    service = RecommendationService()

    # User who owns an air purifier and wears a mask outdoors
    equipped_profile = UserProfile(has_air_purifier=True, uses_mask_outdoors=True)
    equipped_result = service._fallback_recommendations(
        aqi=140, user_profile=equipped_profile
    )

    equipped_tips = " ".join(equipped_result.protection_tips).lower()
    assert "air purifier" in equipped_tips
    assert "mask" in equipped_tips

    # User without purifier or mask
    unequipped_profile = UserProfile(has_air_purifier=False, uses_mask_outdoors=False)
    unequipped_result = service._fallback_recommendations(
        aqi=140, user_profile=unequipped_profile
    )

    unequipped_tips = " ".join(unequipped_result.protection_tips).lower()
    assert "closed" in unequipped_tips or "respirator" in unequipped_tips


# ==============================================================================
# Gemini Prompt & Failure Handling Tests
# ==============================================================================


def test_gemini_prompt_includes_user_profile():
    """Verify that user profile details are passed into the Gemini prompt."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="student",
        household_members=["children", "infants"],
        sensitivity_considerations="asthma",
        exercise_habits="outdoor",
        has_air_purifier=True,
        uses_mask_outdoors=True,
    )

    # Fake successful Gemini response
    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Move workouts indoors.", '
        '"sensitive_groups": "Asthma individuals monitor symptoms.", '
        '"protection_tips": ["Run your air purifier indoors.", "Wear an N95 outside."], '
        '"summary": "Moderate air quality requires attention.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=120,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 45.0, "pm10": 80.0},
        user_profile=profile,
    )

    assert result.source == "gemini"
    assert mock_client.models.generate_content.called

    prompt_used = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert "student" in prompt_used
    assert "asthma" in prompt_used
    assert "children" in prompt_used
    assert "outdoor" in prompt_used
    assert "Yes" in prompt_used  # has purifier / uses mask


def test_gemini_failure_triggers_profile_aware_fallback():
    """Verify that if Gemini throws an error, fallback executes with user profile."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    mock_client.models.generate_content.side_effect = RuntimeError("Quota exhausted")

    profile = UserProfile(
        has_air_purifier=True,
        sensitivity_considerations="asthma",
    )

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=130,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 50.0},
        user_profile=profile,
    )

    assert result.source == "fallback"
    assert len(result.protection_tips) >= 1
    tips_text = " ".join(result.protection_tips).lower()
    assert "air purifier" in tips_text


# ==============================================================================
# API Endpoint Integration Tests
# ==============================================================================


def _fake_air_quality_response():
    """Helper returning a mock AirQualityResponse."""
    return AirQualityResponse(
        location=Location(
            name="Bengaluru",
            latitude=12.97,
            longitude=77.59,
            country="India",
        ),
        current=AirQualityCurrent(
            timestamp="2026-11-23T10:00",
            us_aqi=AQIInfo(
                value=85,
                category="Moderate",
                description="Air quality is acceptable.",
                color="#eab308",
            ),
            pollutants=PollutantValues(pm2_5=28.0, pm10=55.0),
            units={"pm2_5": "µg/m³"},
        ),
        summary="Air quality in Bengaluru is Moderate.",
    )


def test_get_recommendations_endpoint_backward_compatible():
    """Verify GET /api/recommendations functions with city only."""
    with patch("backend.main.OpenMeteoService") as mock_cls:
        mock_svc = MagicMock()
        async def _mock_get_aq(city):
            return _fake_air_quality_response()
        mock_svc.get_air_quality_by_city = _mock_get_aq
        mock_cls.return_value.__aenter__.return_value = mock_svc
        mock_cls.return_value.__aexit__.return_value = None

        result = run_async(get_recommendations(city="Bengaluru"))

        assert result.outdoor_activity
        assert result.summary
        assert len(result.protection_tips) >= 1


def test_get_recommendations_endpoint_with_query_params():
    """Verify GET /api/recommendations accepts user profile query parameters."""
    with patch("backend.main.OpenMeteoService") as mock_cls:
        mock_svc = MagicMock()
        async def _mock_get_aq(city):
            return _fake_air_quality_response()
        mock_svc.get_air_quality_by_city = _mock_get_aq
        mock_cls.return_value.__aenter__.return_value = mock_svc
        mock_cls.return_value.__aexit__.return_value = None

        result = run_async(
            get_recommendations(
                city="Bengaluru",
                lifestyle="student",
                exercise_habits="outdoor",
                sensitivity="asthma",
                has_air_purifier=True,
                uses_mask_outdoors=True,
            )
        )

        assert result.outdoor_activity
        assert len(result.protection_tips) >= 1


def test_post_recommendations_endpoint_with_profile():
    """Verify POST /api/recommendations processes city and structured UserProfile."""
    with patch("backend.main.OpenMeteoService") as mock_cls:
        mock_svc = MagicMock()
        async def _mock_get_aq(city):
            return _fake_air_quality_response()
        mock_svc.get_air_quality_by_city = _mock_get_aq
        mock_cls.return_value.__aenter__.return_value = mock_svc
        mock_cls.return_value.__aexit__.return_value = None

        payload = RecommendationsRequest(
            city="Bengaluru",
            profile=UserProfile(
                lifestyle="working professional",
                household_members=["children", "infants"],
                sensitivity_considerations="asthma",
                has_air_purifier=True,
            ),
        )

        result = run_async(create_recommendations(payload=payload))

        assert result.outdoor_activity
        assert result.summary
        assert len(result.protection_tips) >= 1


def test_recommendations_endpoint_error_handling():
    """Verify endpoint maps CityNotFoundError to 404, network to 503, upstream to 502."""
    with patch("backend.main.OpenMeteoService") as mock_cls:
        mock_svc = MagicMock()
        mock_cls.return_value.__aenter__.return_value = mock_svc
        mock_cls.return_value.__aexit__.return_value = None

        # Test 404 for missing city
        async def _mock_not_found(city):
            raise CityNotFoundError("City not found")
        mock_svc.get_air_quality_by_city = _mock_not_found

        with pytest.raises(HTTPException) as exc_info_404:
            run_async(get_recommendations(city="NonExistentCityXYZ"))
        assert exc_info_404.value.status_code == 404

        # Test 503 for network failure
        async def _mock_network_err(city):
            raise OpenMeteoNetworkError("Connection timed out")
        mock_svc.get_air_quality_by_city = _mock_network_err

        with pytest.raises(HTTPException) as exc_info_503:
            run_async(get_recommendations(city="Bengaluru"))
        assert exc_info_503.value.status_code == 503

        # Test 502 for upstream API error
        async def _mock_api_err(city):
            raise OpenMeteoAPIError("Service unavailable", 500)
        mock_svc.get_air_quality_by_city = _mock_api_err

        with pytest.raises(HTTPException) as exc_info_502:
            run_async(get_recommendations(city="Bengaluru"))
        assert exc_info_502.value.status_code == 502


# ==============================================================================
# Phase 3 Personalization Accuracy & Semantic Validation Regression Tests
# ==============================================================================


def test_fallback_empty_household_never_mentions_children_or_elderly():
    """Verify empty household_members never mentions unselected groups or ages."""
    service = RecommendationService()
    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],
        sensitivity_considerations="none",
        exercise_habits="indoor",
        has_air_purifier=False,
        uses_mask_outdoors=False,
    )

    forbidden_terms = [
        "child",
        "children",
        "infant",
        "infants",
        "older adult",
        "older adults",
        "elderly",
        "family member",
        "household member",
    ]

    for test_aqi in [45, 85, 135, 175, 250, 350]:
        res = service._fallback_recommendations(aqi=test_aqi, user_profile=profile)
        combined = f"{res.outdoor_activity} {res.sensitive_groups} {' '.join(res.protection_tips)} {res.summary}".lower()

        for term in forbidden_terms:
            assert term not in combined, f"Forbidden term '{term}' found in fallback for AQI {test_aqi}: {combined}"


def test_fallback_selected_household_members_only_mentions_selected():
    """Verify only explicitly selected household members are addressed."""
    service = RecommendationService()
    profile = UserProfile(
        household_members=["children"],
        sensitivity_considerations="none",
    )

    res = service._fallback_recommendations(aqi=135, user_profile=profile)
    combined = f"{res.outdoor_activity} {res.sensitive_groups} {' '.join(res.protection_tips)} {res.summary}".lower()

    # Children should be mentioned
    assert "child" in combined or "children" in combined

    # Unselected groups must not be mentioned
    assert "older adult" not in combined
    assert "elderly" not in combined
    assert "infant" not in combined


def test_fallback_no_commute_assumption_for_working_professional():
    """Verify working professional lifestyle alone never implies a commute or traffic."""
    service = RecommendationService()
    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],
    )

    for test_aqi in [80, 140, 180]:
        res = service._fallback_recommendations(aqi=test_aqi, user_profile=profile)
        combined = f"{res.outdoor_activity} {res.sensitive_groups} {' '.join(res.protection_tips)} {res.summary}".lower()

        assert "commute" not in combined
        assert "commuter" not in combined
        assert "commuting" not in combined
        assert "rush hour" not in combined


def test_fallback_exercise_preference_indoor_and_outdoor():
    """Verify exercise recommendations align with the selected preference."""
    service = RecommendationService()

    indoor_profile = UserProfile(exercise_habits="indoor")
    indoor_res = service._fallback_recommendations(aqi=120, user_profile=indoor_profile)
    assert "indoor" in indoor_res.outdoor_activity.lower()

    outdoor_profile = UserProfile(exercise_habits="outdoor")
    outdoor_res = service._fallback_recommendations(aqi=120, user_profile=outdoor_profile)
    assert "outdoor" in outdoor_res.outdoor_activity.lower()


def test_fallback_mask_accuracy_particles_not_gases():
    """Verify mask advice explains that particulate respirators filter particles, not gases."""
    service = RecommendationService()
    profile = UserProfile(uses_mask_outdoors=True)

    res = service._fallback_recommendations(aqi=140, user_profile=profile)
    tips_text = " ".join(res.protection_tips).lower()

    assert "particle" in tips_text
    assert "not filter gases" in tips_text or "does not filter gases" in tips_text


def test_fallback_no_mask_usage_does_not_push_masks_on_moderate_aqi():
    """Verify mask usage is not pushed on moderate AQI when user does not wear masks."""
    service = RecommendationService()
    profile = UserProfile(uses_mask_outdoors=False)

    res = service._fallback_recommendations(aqi=80, user_profile=profile)
    tips_text = " ".join(res.protection_tips).lower()

    assert "mask" not in tips_text
    assert "respirator" not in tips_text
    assert "n95" not in tips_text


def test_gemini_prompt_empty_household_instructions():
    """Verify prompt instructs Gemini not to mention children or elderly when household is empty."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],
        sensitivity_considerations="none",
        exercise_habits="indoor",
        has_air_purifier=False,
        uses_mask_outdoors=False,
    )

    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Conduct workouts indoors.", '
        '"sensitive_groups": "Air quality is acceptable.", '
        '"protection_tips": ["Keep windows shut."], '
        '"summary": "Moderate air quality.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    service.generate_recommendations(
        city="Bengaluru",
        aqi=90,
        category="Moderate",
        pollutants={"pm2_5": 30.0},
        user_profile=profile,
    )

    prompt_used = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert "None specified" in prompt_used
    assert "Do NOT mention children" in prompt_used
    assert "Do NOT assume a daily commute" in prompt_used


def test_semantic_validation_rejects_unselected_household_members():
    """Verify Gemini response mentioning unselected children is rejected and falls back."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],  # empty
        sensitivity_considerations="none",
    )

    # Gemini hallucinated children
    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Limit outdoor exposure.", '
        '"sensitive_groups": "Children and infants should stay indoors.", '
        '"protection_tips": ["Keep windows closed."], '
        '"summary": "Air quality is unhealthy.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )

    assert result.source == "fallback"
    assert "children" not in result.sensitive_groups.lower()
    assert "infants" not in result.sensitive_groups.lower()


def test_semantic_validation_rejects_commuting_assumption():
    """Verify Gemini response assuming commuting is rejected and falls back."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],
    )

    # Gemini hallucinated commuting advice
    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Exercise indoors.", '
        '"sensitive_groups": "Sensitive individuals take care.", '
        '"protection_tips": ["Avoid traffic during your daily commute."], '
        '"summary": "Pollution is elevated.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )

    assert result.source == "fallback"
    assert "commute" not in " ".join(result.protection_tips).lower()


def test_semantic_validation_rejects_gas_mask_claim():
    """Verify Gemini response claiming N95 filters ozone or gases is rejected."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(uses_mask_outdoors=True)

    # Gemini made false claim that mask filters ozone
    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Limit outdoor workouts.", '
        '"sensitive_groups": "Take general precautions.", '
        '"protection_tips": ["Wear an N95 mask to filter ozone and toxic gases."], '
        '"summary": "Air quality is degraded.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )

    assert result.source == "fallback"


def test_semantic_validation_rejects_unsupported_time_claims():
    """Verify Gemini response with unsupported diurnal time claims is rejected."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile()

    # Gemini made unsupported diurnal claim
    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Avoid running outdoors because peak afternoon ozone will be hazardous.", '
        '"sensitive_groups": "Sensitive groups take care.", '
        '"protection_tips": ["Stay indoors."], '
        '"summary": "Ozone alert.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )

    assert result.source == "fallback"


def test_semantic_validation_accepts_valid_grounded_response():
    """Verify valid grounded Gemini response passes semantic validation."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],
        sensitivity_considerations="none",
        exercise_habits="indoor",
        has_air_purifier=False,
        uses_mask_outdoors=False,
    )

    mock_response = MagicMock()
    mock_response.text = (
        '{"outdoor_activity": "Conduct your workouts indoors in a well-ventilated space.", '
        '"sensitive_groups": "Air quality is acceptable for most people today.", '
        '"protection_tips": ["Keep windows closed during periods of outdoor haze."], '
        '"summary": "Air quality is moderate today; indoor routines are ideal.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response

    result = service.generate_recommendations(
        city="Bengaluru",
        aqi=85,
        category="Moderate",
        pollutants={"pm2_5": 28.0},
        user_profile=profile,
    )

    assert result.source == "gemini"
    assert "indoor" in result.outdoor_activity.lower()


def test_semantic_validation_mask_gas_affirmation_vs_negation():
    """Verify 'An N95 filters ozone' is rejected but 'An N95 does not filter ozone' is accepted."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(uses_mask_outdoors=True)

    # 1. False affirmative claim: "An N95 filters ozone" -> must be rejected
    mock_response_false = MagicMock()
    mock_response_false.text = (
        '{"outdoor_activity": "Limit outdoor workouts.", '
        '"sensitive_groups": "Take general precautions.", '
        '"protection_tips": ["An N95 filters ozone and fine particles."], '
        '"summary": "Air quality is degraded.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response_false

    result_false = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )
    assert result_false.source == "fallback"

    # 2. Scientifically accurate negation: "An N95 does not filter ozone" -> must be accepted
    mock_response_true = MagicMock()
    mock_response_true.text = (
        '{"outdoor_activity": "Limit outdoor workouts.", '
        '"sensitive_groups": "Take general precautions.", '
        '"protection_tips": ["An N95 does not filter ozone, but it filters fine particles."], '
        '"summary": "Air quality is degraded.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response_true

    result_true = service.generate_recommendations(
        city="Bengaluru",
        aqi=140,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 55.0},
        user_profile=profile,
    )
    assert result_true.source == "gemini"
    assert "does not filter ozone" in " ".join(result_true.protection_tips).lower()


def test_semantic_validation_allows_explicit_household_exclusion():
    """Verify explicit non-presence/exclusion statements for unselected groups pass."""
    service = RecommendationService()
    mock_client = MagicMock()
    service.client = mock_client

    profile = UserProfile(
        lifestyle="working professional",
        household_members=[],  # empty
        sensitivity_considerations="none",
        exercise_habits="indoor",
    )

    # 1. Clear exclusion statement: "No children were specified" -> accepted
    mock_response_exclusion = MagicMock()
    mock_response_exclusion.text = (
        '{"outdoor_activity": "Maintain your indoor workout routine.", '
        '"sensitive_groups": "No children were specified in the profile; general guidance applies.", '
        '"protection_tips": ["Keep windows closed during periods of haze."], '
        '"summary": "Air quality is elevated today.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response_exclusion

    result_exclusion = service.generate_recommendations(
        city="Bengaluru",
        aqi=130,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 48.0},
        user_profile=profile,
    )
    assert result_exclusion.source == "gemini"
    assert "no children were specified" in result_exclusion.sensitive_groups.lower()

    # 2. Directed advice for unselected group: "Children should stay inside" -> rejected
    mock_response_advice = MagicMock()
    mock_response_advice.text = (
        '{"outdoor_activity": "Maintain your indoor workout routine.", '
        '"sensitive_groups": "Children should stay inside and avoid active play.", '
        '"protection_tips": ["Keep windows closed during periods of haze."], '
        '"summary": "Air quality is elevated today.", "source": "gemini"}'
    )
    mock_client.models.generate_content.return_value = mock_response_advice

    result_advice = service.generate_recommendations(
        city="Bengaluru",
        aqi=130,
        category="Unhealthy for Sensitive Groups",
        pollutants={"pm2_5": 48.0},
        user_profile=profile,
    )
    assert result_advice.source == "fallback"
    assert "children" not in result_advice.sensitive_groups.lower()

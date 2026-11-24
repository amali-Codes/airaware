import os
import re
from typing import Optional
import logging

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from backend.schemas.recommendations import AIRecommendations
from backend.schemas.user_profile import UserProfile

logger = logging.getLogger(__name__)
load_dotenv()


class RecommendationService:
    """Generate recommendations using Gemini with a personalized rule-based fallback."""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model = "gemini-3.5-flash-lite"

    def _validate_recommendations_against_profile(
        self,
        rec: AIRecommendations,
        profile: UserProfile,
        pollutants: Optional[dict] = None,
    ) -> bool:
        """
        Validate that AI-generated recommendations strictly adhere to user profile constraints.
        Returns True if valid, False if any constraint is violated (triggering fallback).
        """
        combined_text = (
            f"{rec.outdoor_activity} {rec.sensitive_groups} "
            f"{' '.join(rec.protection_tips)} {rec.summary}"
        ).lower()

        # Helper to check if a matched household term is a legitimate non-presence / exclusion statement
        # (e.g. "No children were specified" vs "Children should stay indoors")
        def _is_household_exclusion(term_match) -> bool:
            start, end = term_match.span()
            prefix = combined_text[max(0, start - 40):start]
            suffix = combined_text[end:min(len(combined_text), end + 40)]
            if re.search(r"\b(no|zero|without|neither)\s+(other\s+|additional\s+|specific\s+|vulnerable\s+)?$", prefix):
                return True
            if re.search(r"^\s*(were|was|are|is)?\s*(not\s+specified|not\s+listed|not\s+present|not\s+selected|unspecified|none)\b", suffix):
                return True
            return False

        def _has_unauthorized_household_mention(pattern: str) -> bool:
            for m in re.finditer(pattern, combined_text):
                if not _is_household_exclusion(m):
                    return True
            return False

        # 1. Household constraints:
        household_selected = set(profile.household_members)

        # Children check if not selected
        if "children" not in household_selected:
            if _has_unauthorized_household_mention(r"\b(children|child|kids?|toddlers?)\b"):
                return False

        # Infants check if not selected
        if "infants" not in household_selected:
            if _has_unauthorized_household_mention(r"\b(infants?|babies|baby)\b"):
                return False

        # Elderly check if not selected
        if "elderly people" not in household_selected:
            if _has_unauthorized_household_mention(r"\b(elderly|older adults?|seniors?)\b"):
                return False

        # When NO household members are specified at all:
        if len(household_selected) == 0:
            if _has_unauthorized_household_mention(r"\b(family members?|household members?)\b"):
                return False

        # 2. Lifestyle / Commuting assumptions:
        # Lifestyle alone must never imply a commute, transit, or fixed office hours
        if re.search(r"\b(daily commute|commuters?|commuting|transit to (work|office|school)|office commute|morning rush hour|evening rush hour|rush[- ]hour traffic)\b", combined_text):
            return False

        # 3. Time-of-day unsupported claims (without hourly data):
        if re.search(r"\b(peak afternoon ozone|afternoon ozone peaks?|ozone peaks in the afternoon|afternoon peak for ozone|rush[- ]hour peak|peak morning pollution)\b", combined_text):
            return False

        # 4. Mask and Gas physical filtration accuracy:
        # Particulate respirators filter particles, NOT gases or ozone.
        # Only reject affirmative claims that masks filter/block/protect against gases/ozone.
        # Statements explaining that masks DO NOT filter gases are scientifically accurate and permitted.
        for m in re.finditer(
            r"\b(masks?|respirators?|n95|kn95)\b([^.!?;\n]*?)\b(filters?|blocks?|protects? against|protect against)\b([^.!?;\n]*?)\b(ozone|gases|gas|no2|so2|carbon monoxide|co\b)",
            combined_text,
        ):
            pre_verb = m.group(2)
            pre_gas = m.group(4)
            if not re.search(r"\b(not|n't|cannot|can't|no|never|unable to|without)\b", pre_verb) and not re.search(r"\b(not|n't|no|never)\b", pre_gas):
                return False

        for m in re.finditer(
            r"\b(filters?|blocks?|protects? against|protect against)\b([^.!?;\n]*?)\b(ozone|gases|gas|no2|so2|carbon monoxide)\b([^.!?;\n]*?)\b(with an?|using an?|through an?)\b\s*(masks?|respirators?|n95|kn95)",
            combined_text,
        ):
            pre_verb = combined_text[max(0, m.start() - 25):m.start()]
            pre_gas = m.group(2)
            if not re.search(r"\b(not|n't|cannot|can't|no|never|unable to|without)\b", pre_verb) and not re.search(r"\b(not|n't|cannot|can't|no|never|unable to|without)\b", pre_gas):
                return False

        # 5. User does not wear mask - must not falsely claim user already wears a mask:
        if not profile.uses_mask_outdoors:
            if re.search(r"\b(continue wearing your mask|as you (already|usually|normally) wear|your usual mask|your regular mask)\b", combined_text):
                return False

        return True

    def _fallback_recommendations(
        self,
        aqi: int,
        user_profile: Optional[UserProfile] = None,
        pollutants: Optional[dict] = None,
    ) -> AIRecommendations:
        """
        Provide rule-based recommendations tailored strictly to US AQI levels and the user's living profile.
        Keeps guidance non-diagnostic, practical, and strictly aligned with profile constraints.
        """
        profile = user_profile or UserProfile()

        # Sensitive conditions
        has_asthma = profile.sensitivity_considerations == "asthma"
        has_allergies = profile.sensitivity_considerations == "allergies"
        has_respiratory = profile.sensitivity_considerations in ("respiratory sensitivity", "asthma")

        sensitive_notes = []
        if has_asthma:
            sensitive_notes.append("individuals with asthma should monitor for breathing discomfort and limit strenuous exertion")
        elif has_allergies:
            sensitive_notes.append("individuals with particulate or seasonal allergies should monitor symptoms and limit prolonged exposure")
        elif has_respiratory:
            sensitive_notes.append("individuals with respiratory sensitivity should take precautions to reduce exposure")

        # Household members - strictly only add for explicitly selected members
        if "infants" in profile.household_members:
            sensitive_notes.append("infants should remain in clean indoor air")
        if "children" in profile.household_members:
            sensitive_notes.append("children should take more rest breaks during outdoor activities")
        if "elderly people" in profile.household_members:
            sensitive_notes.append("older adults should limit strenuous physical exertion")

        # Exercise habits
        exercise_pref = profile.exercise_habits

        def get_activity_guidance(level: str) -> str:
            if level == "good":
                if exercise_pref == "indoor":
                    return "Air quality is good. Indoor air conditions are optimal for your indoor workout routine."
                elif exercise_pref == "outdoor":
                    return "Air quality is good. It is an ideal day for your outdoor workout routine."
                else:
                    return "Air quality is good. Enjoy outdoor activities or your indoor workout routine as usual."
            elif level == "moderate":
                if exercise_pref == "indoor":
                    return "Air quality is acceptable. Maintain your usual indoor exercise routine."
                elif exercise_pref == "outdoor":
                    return "Conditions are acceptable for outdoor workouts. Take breaks if you notice fatigue or discomfort."
                else:
                    return "Conditions are acceptable for outdoor activities and exercise. Monitor breathing comfort during longer workouts."
            elif level == "sensitive":
                if exercise_pref == "indoor":
                    return "Air quality is degraded outdoors. Stick to your indoor workouts and keep indoor air clean."
                elif exercise_pref == "outdoor":
                    return "Consider reducing outdoor workout intensity or moving strenuous cardiovascular exercise indoors."
                else:
                    return "Favor indoor exercise over outdoor workouts today to minimize exposure to elevated pollution."
            elif level == "unhealthy":
                if exercise_pref == "indoor":
                    return "Avoid outdoor activities. Conduct all workouts indoors with doors and windows closed."
                elif exercise_pref == "outdoor":
                    return "Avoid outdoor workouts. Move all cardiovascular exercise indoors to protect lung health."
                else:
                    return "Move all exercise indoors and keep windows closed to limit outdoor air exposure."
            else:  # very unhealthy / hazardous
                if exercise_pref == "indoor":
                    return "Avoid all outdoor exertion. Rest indoors with windows and doors securely closed."
                elif exercise_pref == "outdoor":
                    return "Hazardous conditions: Avoid all outdoor activities and remain strictly indoors."
                else:
                    return "Hazardous conditions: Avoid all outdoor exertion and remain strictly indoors."

        is_pm_elevated = (aqi > 100) or bool(
            pollutants and ((pollutants.get("pm2_5") or 0) > 35 or (pollutants.get("pm10") or 0) > 50)
        )

        # ----------------------------------------------------------------------
        # AQI <= 50 (Good)
        # ----------------------------------------------------------------------
        if aqi <= 50:
            outdoor_act = get_activity_guidance("good")
            if sensitive_notes:
                sensitive_msg = f"Air quality is satisfactory. {'; '.join(sensitive_notes)}."
            else:
                sensitive_msg = "Air quality is satisfactory. No special precautions are needed."

            tips = [
                "Continue your normal daily routine and exercise.",
                "Stay well hydrated throughout the day.",
            ]
            if profile.has_air_purifier:
                tips.append("Indoor air quality is generally clean; natural ventilation is fine today.")
            else:
                tips.append("Good time to open windows and let fresh air circulate indoors.")

            return AIRecommendations(
                outdoor_activity=outdoor_act,
                sensitive_groups=sensitive_msg,
                protection_tips=tips[:5],
                summary="Air quality is good. It is a suitable time to enjoy everyday activities.",
                source="fallback",
            )

        # ----------------------------------------------------------------------
        # AQI <= 100 (Moderate)
        # ----------------------------------------------------------------------
        if aqi <= 100:
            outdoor_act = get_activity_guidance("moderate")
            if sensitive_notes:
                sensitive_msg = f"Unusually sensitive individuals should monitor how they feel: {'; '.join(sensitive_notes)}."
            else:
                sensitive_msg = "Air quality is acceptable for most people. Unusually sensitive individuals should monitor how they feel."

            tips = [
                "Pay attention to any breathing discomfort or fatigue.",
            ]
            if has_asthma:
                tips.append("Take frequent rest breaks and monitor your breathing comfort during physical activity.")
            elif has_allergies:
                tips.append("Rinse eyes and change clothes after returning from outdoors.")
            else:
                tips.append("Reduce prolonged outdoor exertion if you feel unusual fatigue.")

            if profile.has_air_purifier:
                tips.append("Run your air purifier on low or eco mode if sensitive individuals are present.")

            if profile.uses_mask_outdoors:
                tips.append("Outdoor mask wearing is optional today; particulate respirators help near dusty roads (note: particulate masks filter particles, not gases).")

            return AIRecommendations(
                outdoor_activity=outdoor_act,
                sensitive_groups=sensitive_msg,
                protection_tips=tips[:5],
                summary="Air quality is acceptable. Unusually sensitive individuals should monitor how they feel.",
                source="fallback",
            )

        # ----------------------------------------------------------------------
        # AQI <= 150 (Unhealthy for Sensitive Groups)
        # ----------------------------------------------------------------------
        if aqi <= 150:
            outdoor_act = get_activity_guidance("sensitive")
            if sensitive_notes:
                sensitive_msg = f"Elevated pollution poses higher risk for sensitive individuals: {'; '.join(sensitive_notes)}."
            else:
                sensitive_msg = "Elevated pollution may affect sensitive individuals. Anyone experiencing discomfort should reduce prolonged exertion."

            tips = [
                "Move intense cardiovascular exercise indoors.",
                "Keep windows and doors closed to avoid pulling polluted outdoor air inside.",
            ]
            if profile.has_air_purifier:
                tips.append("Run your air purifier in bedrooms and main living spaces.")
            else:
                tips.append("Keep doors and windows closed to reduce outdoor particle entry.")

            if profile.uses_mask_outdoors:
                tips.append("Wear your well-fitting particulate respirator (such as an N95/KN95) outdoors to filter fine particles like PM2.5 (note: particulate masks do not filter gases like ozone or NO2).")
            elif is_pm_elevated:
                tips.append("If prolonged outdoor exposure is unavoidable, a well-fitting particulate respirator (such as N95) can filter airborne particles like PM2.5 and PM10 (note: particulate respirators do not filter gases like ozone).")

            if has_asthma:
                tips.append("Follow your personal asthma action plan and move physical activities indoors.")

            return AIRecommendations(
                outdoor_activity=outdoor_act,
                sensitive_groups=sensitive_msg,
                protection_tips=tips[:5],
                summary="Air quality is elevated. Sensitive individuals should take precautions outdoors.",
                source="fallback",
            )

        # ----------------------------------------------------------------------
        # AQI <= 200 (Unhealthy)
        # ----------------------------------------------------------------------
        if aqi <= 200:
            outdoor_act = get_activity_guidance("unhealthy")
            if sensitive_notes:
                sensitive_msg = f"Sensitive groups should avoid outdoor exertion: {'; '.join(sensitive_notes)}."
            else:
                sensitive_msg = "Unhealthy air quality. Sensitive individuals should avoid outdoor exertion, and everyone should limit prolonged outdoor exposure."

            tips = [
                "Move all exercise indoors.",
                "Keep windows and exterior doors shut tight.",
            ]
            if profile.has_air_purifier:
                tips.append("Run your indoor air purifier on a higher fan speed in main living areas.")
            else:
                tips.append("Stay indoors with closed windows; consider establishing a clean-air room with filtered air.")

            if profile.uses_mask_outdoors:
                tips.append("Wear your particulate respirator (N95/KN95) outdoors to filter fine particles (note: particulate masks do not filter gases like ozone or NO2).")
            else:
                tips.append("If outdoor exposure is necessary, a well-fitting particulate respirator (N95/KN95) filters airborne particles like PM2.5 and PM10 (note: particulate respirators do not filter gases).")

            return AIRecommendations(
                outdoor_activity=outdoor_act,
                sensitive_groups=sensitive_msg,
                protection_tips=tips[:5],
                summary="Air quality is unhealthy. Minimize outdoor exposure and protect your respiratory comfort.",
                source="fallback",
            )

        # ----------------------------------------------------------------------
        # AQI <= 300 (Very Unhealthy)
        # ----------------------------------------------------------------------
        if aqi <= 300:
            outdoor_act = get_activity_guidance("very_unhealthy")
            if sensitive_notes:
                sensitive_msg = f"Health alert: Serious risk. Strictly indoor rest advised for: {'; '.join(sensitive_notes)}."
            else:
                sensitive_msg = "Health alert: Serious risk. Sensitive individuals should remain indoors; everyone should avoid outdoor physical exertion."

            tips = [
                "Stay indoors and keep all windows and doors closed.",
                "Avoid any outdoor exercise or heavy exertion.",
            ]
            if profile.has_air_purifier:
                tips.append("Operate air filtration continuously in closed rooms.")
            else:
                tips.append("Remain inside and avoid introducing indoor smoke, candles, or vacuuming.")

            if profile.uses_mask_outdoors:
                tips.append("Wear a well-fitting particulate respirator (N95) if stepping outside (note: particulate respirators filter particles, not gases).")
            else:
                tips.append("If stepping outside is unavoidable, an N95 particulate respirator filters airborne particles (note: particulate respirators do not filter gases).")

            return AIRecommendations(
                outdoor_activity=outdoor_act,
                sensitive_groups=sensitive_msg,
                protection_tips=tips[:5],
                summary="Air quality is very unhealthy. Take immediate protective measures and stay indoors.",
                source="fallback",
            )

        # ----------------------------------------------------------------------
        # AQI > 300 (Hazardous)
        # ----------------------------------------------------------------------
        if sensitive_notes:
            sensitive_msg = f"Emergency conditions: All individuals, especially {'; '.join(sensitive_notes)}, must remain indoors."
        else:
            sensitive_msg = "Emergency conditions: Entire population is at high risk. Avoid outdoor exposure and remain indoors."

        return AIRecommendations(
            outdoor_activity="Hazardous outdoor conditions: Avoid all outdoor activities and remain strictly indoors.",
            sensitive_groups=sensitive_msg,
            protection_tips=[
                "Stay indoors with all windows and doors sealed.",
                "Operate clean air filtration or purifiers continuously if available.",
                "Avoid all outdoor exercise and strenuous movement.",
                "Wear a sealed particulate respirator (N95) if outdoor exposure is an absolute emergency (note: particulate respirators filter particles, not gases).",
                "Follow all local public health and environmental directives.",
            ],
            summary="Air quality is hazardous. Avoid all outdoor exposure and remain in clean indoor air.",
            source="fallback",
        )

    def generate_recommendations(
        self,
        city: str,
        aqi: int,
        category: str,
        pollutants: dict,
        user_profile: Optional[UserProfile] = None,
    ) -> AIRecommendations:
        """
        Generate practical recommendations using Gemini and real AQI data, personalized to the user profile,
        with strict semantic validation and graceful fallback.
        """
        if self.client is None:
            return self._fallback_recommendations(aqi, user_profile, pollutants=pollutants)

        profile = user_profile or UserProfile()

        # Format household members clearly
        if profile.household_members:
            household_str = ", ".join(profile.household_members)
            household_instruction = (
                f"- Household Members: {household_str}\n"
                f"  STRICT CONSTRAINT: ONLY mention the specific household members explicitly listed here ({household_str}). "
                f"Do NOT mention any unlisted groups (for example, do not mention children, infants, elderly, older adults, or family members if they are not listed above)."
            )
        else:
            household_instruction = (
                "- Household Members: None specified\n"
                "  STRICT CONSTRAINT: No household members were specified. Do NOT assume the user lives alone. "
                "Do NOT mention children, infants, elderly people, older adults, or family members."
            )

        # Format mask usage constraint
        if profile.uses_mask_outdoors:
            mask_instruction = (
                "- Uses Mask Outdoors: Yes\n"
                "  Guidance: The user wears a mask outdoors. Advise whether wearing a well-fitting particulate respirator (such as N95/KN95) "
                "is beneficial outdoors today based on actual particulate readings. Clearly explain that particulate respirators filter airborne particles "
                "(PM2.5, PM10), NOT gaseous pollutants (such as ozone, NO2, SO2, or CO)."
            )
        else:
            mask_instruction = (
                "- Uses Mask Outdoors: No\n"
                "  STRICT CONSTRAINT: The user does NOT regularly wear a mask outdoors. Never imply or state that they already wear a mask. "
                "Do not push mask usage unnecessarily for good or moderate air. If elevated particulate pollution (PM2.5/PM10) makes a respirator "
                "advisable for outdoor exposure, mention an N95/KN95 as an option while explaining that particulate respirators filter airborne particles, "
                "NOT gaseous pollutants like ozone, NO2, SO2, or CO."
            )

        # Format exercise instruction
        exercise_instruction = (
            f"- Exercise Habits: {profile.exercise_habits}\n"
            f"  STRICT CONSTRAINT: Respect their exercise preference ({profile.exercise_habits}). "
            f"If indoor, focus advice on indoor workouts and indoor air quality. If outdoor, address outdoor workout safety and intensity. If both, cover both."
        )

        # Format lifestyle instruction
        lifestyle_instruction = (
            f"- Daily Routine / Lifestyle: {profile.lifestyle}\n"
            "  STRICT CONSTRAINT: Do NOT assume a daily commute, rush hour travel, campus attendance, or fixed office hours based on lifestyle alone."
        )

        profile_details = f"""
User Living Profile:
{lifestyle_instruction}
{household_instruction}
- Health / Respiratory Sensitivities: {profile.sensitivity_considerations}
{exercise_instruction}
- Has Indoor Air Purifier: {"Yes" if profile.has_air_purifier else "No"}
{mask_instruction}
"""

        prompt = f"""
        You are a personalized air quality health and wellness assistant for AirAware.

        Analyze the actual current air quality data and personalize your guidance according to the user's specific living profile.

        Actual Air Quality Information (DO NOT invent, exaggerate, or alter measurements):
        - City: {city}
        - US AQI: {aqi}
        - AQI Category: {category}
        - Pollutant Readings: {pollutants}

        {profile_details}

        Personalization Guidelines:
        1. Outdoor Activity: Adapt advice directly to their exercise habits ({profile.exercise_habits}) without assuming commuting or fixed travel schedules.
        2. Sensitive Groups: Address their specific sensitivities ({profile.sensitivity_considerations}) and only the household members explicitly listed ({', '.join(profile.household_members) if profile.household_members else 'None specified'}). If no household members are specified, do NOT mention children, infants, elderly, older adults, or family members.
        3. Protection Tips:
           - Provide between 1 and 5 actionable, prioritized tips.
           - If they have an air purifier, advise on running/optimizing it indoors when pollution is elevated. If not, suggest practical ways to minimize indoor exposure.
           - If mask advice is given, clarify that particulate respirators (like N95/KN95) filter airborne particles (PM2.5/PM10) and do NOT filter gases (ozone, NO2, SO2, CO). Never claim a user already wears a mask if uses_mask_outdoors is No.
        4. Summary: Deliver a concise, empathetic overview highlighting what this air quality means for them today.

        Grounding and Safety Rules:
        - Base ALL health and activity advice strictly on the actual AQI ({aqi}) and pollutant readings.
        - Never invent air quality numbers, never change units, never diagnose medical conditions, and never prescribe medication.
        - Time-of-Day Grounding: You only have current snapshot data. STRICTLY FORBIDDEN to make unverified diurnal or time-of-day claims (e.g. do NOT claim ozone peaks in the afternoon, or pollution peaks during rush hour).
        - Mask Accuracy: Particulate respirators filter airborne particulates (PM2.5, PM10) and do NOT filter gaseous pollutants (ozone, NO2, SO2, CO).
        - Household Scope: STRICTLY FORBIDDEN to mention children, infants, elderly people, older adults, or family members unless explicitly listed in Household Members.
        - Commute Assumption: STRICTLY FORBIDDEN to assume commuting or rush-hour transit based on lifestyle.
        - Avoid generic instructions such as prescribing or keeping emergency inhalers ready, and avoid claiming urgent medical care is required solely based on AQI values.
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

            parsed = AIRecommendations.model_validate_json(response.text)
            parsed.source = "gemini"

            # Semantic validation against profile constraints
            if not self._validate_recommendations_against_profile(parsed, profile, pollutants):
                return self._fallback_recommendations(aqi, user_profile, pollutants=pollutants)

            return parsed

        except Exception as exc:
                    logger.exception(
                "Gemini recommendation generation failed: %s: %s",
                type(exc).__name__,
                exc,
            )
                    return self._fallback_recommendations(
                aqi, user_profile, pollutants=pollutants
            )

import unittest
from pydantic import ValidationError

from backend.schemas.user_profile import UserProfile


class TestUserProfile(unittest.TestCase):
    """Unit tests for the UserProfile Pydantic schema."""

    def test_default_values(self):
        """Verify that default profile initializes with expected baseline values."""
        profile = UserProfile()

        self.assertEqual(profile.lifestyle, "other")
        self.assertEqual(profile.household_members, ["adults"])
        self.assertEqual(profile.sensitivity_considerations, "none")
        self.assertEqual(profile.exercise_habits, "both")
        self.assertFalse(profile.has_air_purifier)
        self.assertFalse(profile.uses_mask_outdoors)

        # Verify convenience properties
        self.assertEqual(profile.sensitivity, "none")
        self.assertFalse(profile.mask_outdoors)

    def test_valid_custom_profile(self):
        """Verify profile creation with custom valid values across all fields."""
        profile = UserProfile(
            lifestyle="working professional",
            household_members=["adults", "children", "elderly people"],
            sensitivity_considerations="asthma",
            exercise_habits="outdoor",
            has_air_purifier=True,
            uses_mask_outdoors=True,
        )

        self.assertEqual(profile.lifestyle, "working professional")
        self.assertEqual(
            profile.household_members,
            ["adults", "children", "elderly people"],
        )
        self.assertEqual(profile.sensitivity_considerations, "asthma")
        self.assertEqual(profile.exercise_habits, "outdoor")
        self.assertTrue(profile.has_air_purifier)
        self.assertTrue(profile.uses_mask_outdoors)

        # Verify dict dump contains all custom fields
        data = profile.model_dump()
        self.assertEqual(data["lifestyle"], "working professional")
        self.assertEqual(data["sensitivity_considerations"], "asthma")
        self.assertTrue(data["has_air_purifier"])
        self.assertTrue(data["uses_mask_outdoors"])

    def test_lifestyle_normalization(self):
        """Verify lifestyle normalizes underscores, whitespace, and letter case."""
        # Underscore normalization
        p1 = UserProfile(lifestyle="working_professional")
        self.assertEqual(p1.lifestyle, "working professional")

        # Mixed-case and whitespace normalization
        p2 = UserProfile(lifestyle="  Student  ")
        self.assertEqual(p2.lifestyle, "student")

        p3 = UserProfile(lifestyle="HOMEMAKER")
        self.assertEqual(p3.lifestyle, "homemaker")

        p4 = UserProfile(lifestyle="Retired")
        self.assertEqual(p4.lifestyle, "retired")

    def test_household_member_normalization(self):
        """Verify household members accept single string, clean whitespace, and map variations."""
        # Single string gets converted into a list
        p1 = UserProfile(household_members="children")
        self.assertEqual(p1.household_members, ["children"])

        # Mapping 'elderly' and 'elderly_people' to 'elderly people'
        p2 = UserProfile(household_members=["elderly", "infants"])
        self.assertEqual(p2.household_members, ["elderly people", "infants"])

        p3 = UserProfile(household_members=["elderly_people"])
        self.assertEqual(p3.household_members, ["elderly people"])

        # Case and whitespace trimming
        p4 = UserProfile(household_members=["  Adults  ", "CHILDREN"])
        self.assertEqual(p4.household_members, ["adults", "children"])

    def test_sensitivity_normalization(self):
        """Verify sensitivity normalizes case, None, underscores, and list inputs."""
        # Case and whitespace trimming
        p1 = UserProfile(sensitivity_considerations="  Allergies  ")
        self.assertEqual(p1.sensitivity_considerations, "allergies")

        # Underscore variant
        p2 = UserProfile(sensitivity_considerations="respiratory_sensitivity")
        self.assertEqual(p2.sensitivity_considerations, "respiratory sensitivity")

        p3 = UserProfile(sensitivity_considerations="respiratory")
        self.assertEqual(p3.sensitivity_considerations, "respiratory sensitivity")

        # None explicitly passed defaults to 'none'
        p4 = UserProfile(sensitivity_considerations=None)
        self.assertEqual(p4.sensitivity_considerations, "none")

        # List input: current implementation takes the first item
        p5 = UserProfile(sensitivity_considerations=["asthma", "allergies"])
        self.assertEqual(p5.sensitivity_considerations, "asthma")

        p6 = UserProfile(sensitivity_considerations=[])
        self.assertEqual(p6.sensitivity_considerations, "none")

    def test_exercise_habit_normalization(self):
        """Verify exercise habit strips whitespace and normalizes case."""
        p1 = UserProfile(exercise_habits="  Indoor  ")
        self.assertEqual(p1.exercise_habits, "indoor")

        p2 = UserProfile(exercise_habits="OUTDOOR")
        self.assertEqual(p2.exercise_habits, "outdoor")

        p3 = UserProfile(exercise_habits="Both")
        self.assertEqual(p3.exercise_habits, "both")

    def test_rejection_of_invalid_literal_values(self):
        """Verify that values outside defined Literal choices raise ValidationError."""
        # Invalid lifestyle
        with self.assertRaises(ValidationError):
            UserProfile(lifestyle="unemployed")

        with self.assertRaises(ValidationError):
            UserProfile(lifestyle="astronaut")

        # Invalid household member
        with self.assertRaises(ValidationError):
            UserProfile(household_members=["pets"])

        with self.assertRaises(ValidationError):
            UserProfile(household_members=["adults", "teenagers"])

        # Invalid sensitivity
        with self.assertRaises(ValidationError):
            UserProfile(sensitivity_considerations="diabetes")

        with self.assertRaises(ValidationError):
            UserProfile(sensitivity_considerations="cardiovascular")

        # Invalid exercise habit
        with self.assertRaises(ValidationError):
            UserProfile(exercise_habits="gym")

        with self.assertRaises(ValidationError):
            UserProfile(exercise_habits="swimming")

    def test_boolean_fields_and_properties(self):
        """Verify boolean fields accept boolean values and properties mirror them correctly."""
        p_false = UserProfile(has_air_purifier=False, uses_mask_outdoors=False)
        self.assertIs(p_false.has_air_purifier, False)
        self.assertIs(p_false.uses_mask_outdoors, False)
        self.assertIs(p_false.mask_outdoors, False)

        p_true = UserProfile(has_air_purifier=True, uses_mask_outdoors=True)
        self.assertIs(p_true.has_air_purifier, True)
        self.assertIs(p_true.uses_mask_outdoors, True)
        self.assertIs(p_true.mask_outdoors, True)


if __name__ == "__main__":
    unittest.main()

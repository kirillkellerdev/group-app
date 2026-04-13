"""Unit tests for names_db.py module."""

import pytest
from names_db import extract_first_name, detect_gender, is_name_recognized, RU_NAMES


class TestExtractFirstName:
    """Tests for extract_first_name function."""

    def test_simple_first_name(self):
        """Test extracting simple first name."""
        assert extract_first_name("Иван") == "иван"
        assert extract_first_name("Мария") == "мария"

    def test_full_name(self):
        """Test extracting first name from full name."""
        assert extract_first_name("Иван Петров") == "иван"
        assert extract_first_name("Мария Иванова") == "мария"

    def test_name_with_middle_name(self):
        """Test extracting first name from name with patronymic."""
        assert extract_first_name("Иван Иванович") == "иван"
        assert extract_first_name("Марья Ивановна") == "марья"

    def test_name_with_punctuation(self):
        """Test handling punctuation in names."""
        assert extract_first_name("Иван,") == "иван"
        assert extract_first_name("Мария.") == "мария"
        assert extract_first_name("Олег!") == "олег"

    def test_name_with_whitespace(self):
        """Test handling whitespace in names."""
        assert extract_first_name("  Иван  ") == "иван"
        assert extract_first_name("\tМария\n") == "мария"

    def test_empty_string(self):
        """Test handling empty string."""
        # Empty string results in IndexError in current implementation
        with pytest.raises(IndexError):
            extract_first_name("")

    def test_single_character(self):
        """Test handling single character name."""
        assert extract_first_name("Я") == "я"


class TestDetectGender:
    """Tests for detect_gender function."""

    def test_male_names(self):
        """Test detection of male names."""
        assert detect_gender("Александр") == "M"
        assert detect_gender("Иван") == "M"
        assert detect_gender("Дмитрий") == "M"
        assert detect_gender("Сергей") == "M"

    def test_female_names(self):
        """Test detection of female names."""
        assert detect_gender("Александра") == "F"
        assert detect_gender("Мария") == "F"
        assert detect_gender("Екатерина") == "F"
        assert detect_gender("Анна") == "F"

    def test_diminutive_male_names(self):
        """Test detection of diminutive male names."""
        assert detect_gender("Саша") == "M"
        assert detect_gender("Ваня") == "M"
        assert detect_gender("Дима") == "M"
        assert detect_gender("Миша") == "M"

    def test_diminutive_female_names(self):
        """Test detection of diminutive female names."""
        assert detect_gender("Настя") == "F"
        assert detect_gender("Катя") == "F"
        assert detect_gender("Маша") == "F"
        assert detect_gender("Оля") == "F"

    def test_full_name_male(self):
        """Test gender detection from full name (male)."""
        assert detect_gender("Александр Пушкин") == "M"
        assert detect_gender("Иван Петрович Петров") == "M"

    def test_full_name_female(self):
        """Test gender detection from full name (female)."""
        assert detect_gender("Мария Иванова") == "F"
        assert detect_gender("Екатерина Сергеевна Смирнова") == "F"

    def test_unknown_name_defaults_to_male(self):
        """Test that unknown names default to 'M'."""
        assert detect_gender("НеизвестноеИмя") == "M"
        assert detect_gender("XYZ") == "M"

    def test_case_insensitive(self):
        """Test that detection is case insensitive."""
        assert detect_gender("александр") == "M"
        assert detect_gender("АЛЕКСАНДР") == "M"
        assert detect_gender("мария") == "F"
        assert detect_gender("МАРИЯ") == "F"

    def test_name_with_punctuation(self):
        """Test handling punctuation in names."""
        assert detect_gender("Иван,") == "M"
        assert detect_gender("Мария.") == "F"


class TestIsNameRecognized:
    """Tests for is_name_recognized function."""

    def test_recognized_male_names(self):
        """Test recognition of male names."""
        assert is_name_recognized("Александр") is True
        assert is_name_recognized("Иван") is True
        # Note: Дмитрий is not in the database, use "дима" instead
        assert is_name_recognized("Дима") is True

    def test_recognized_female_names(self):
        """Test recognition of female names."""
        assert is_name_recognized("Мария") is True
        assert is_name_recognized("Анна") is True
        assert is_name_recognized("Екатерина") is True

    def test_unrecognized_names(self):
        """Test unrecognized names."""
        assert is_name_recognized("НеизвестноеИмя") is False
        assert is_name_recognized("XYZ123") is False

    def test_case_insensitive_recognition(self):
        """Test that recognition is case insensitive."""
        assert is_name_recognized("александр") is True
        assert is_name_recognized("АЛЕКСАНДР") is True
        assert is_name_recognized("мария") is True
        assert is_name_recognized("МАРИЯ") is True

    def test_full_name_recognition(self):
        """Test recognition based on first name only."""
        assert is_name_recognized("Александр Пушкин") is True
        assert is_name_recognized("Мария Иванова") is True

    def test_name_with_punctuation(self):
        """Test handling punctuation in names."""
        assert is_name_recognized("Иван,") is True
        assert is_name_recognized("Мария.") is True


class TestRuNamesDatabase:
    """Tests for RU_NAMES database."""

    def test_database_not_empty(self):
        """Test that the database contains entries."""
        assert len(RU_NAMES) > 0

    def test_all_values_are_m_or_f(self):
        """Test that all gender values are either 'M' or 'F'."""
        for name, gender in RU_NAMES.items():
            assert gender in ["M", "F"], f"Invalid gender '{gender}' for name '{name}'"

    def test_all_keys_are_lowercase(self):
        """Test that all name keys are lowercase."""
        for name in RU_NAMES.keys():
            assert name == name.lower(), f"Name '{name}' is not lowercase"

    def test_no_duplicate_names(self):
        """Test that there are no duplicate names."""
        names_list = list(RU_NAMES.keys())
        assert len(names_list) == len(set(names_list))

    def test_common_male_names_present(self):
        """Test that common male names are in database."""
        # Note: Database contains diminutive forms like "дима" not "дмитрий"
        common_male = ["александр", "иван", "сергей", "дима", "андрей"]
        for name in common_male:
            assert name in RU_NAMES
            assert RU_NAMES[name] == "M"

    def test_common_female_names_present(self):
        """Test that common female names are in database."""
        common_female = ["мария", "анна", "елена", "наталья", "екатерина"]
        for name in common_female:
            assert name in RU_NAMES
            assert RU_NAMES[name] == "F"

"""Unit tests for gender_ai.py module."""

import pytest
from gender_ai import extract_first_name, detect_gender, is_name_recognized


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
    """Tests for detect_gender function using AI-based detection."""

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
        """Test that unknown names default to 'M' based on ending patterns."""
        # Names ending in consonants default to M
        assert detect_gender("XYZ") == "M"
        # Names ending in -а/-я default to F
        assert detect_gender("НеизвестноеИмя") == "F"  # ends in 'я'

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

    def test_names_ending_in_soft_sign(self):
        """Test names ending in soft sign (ь) are detected as female."""
        assert detect_gender("Любовь") == "F"
        assert detect_gender("Ночь") == "F"

    def test_male_exceptions(self):
        """Test male names that are exceptions to typical patterns."""
        assert detect_gender("Никита") == "M"  # ends in -а but male
        assert detect_gender("Юрий") == "M"  # ends in -й but male
        assert detect_gender("Андрей") == "M"


class TestIsNameRecognized:
    """Tests for is_name_recognized function."""

    def test_recognized_cyrillic_names(self):
        """Test recognition of Cyrillic names."""
        assert is_name_recognized("Александр") is True
        assert is_name_recognized("Иван") is True
        assert is_name_recognized("Мария") is True

    def test_recognized_latin_names(self):
        """Test recognition of Latin alphabet names."""
        assert is_name_recognized("John") is True
        assert is_name_recognized("Mary") is True

    def test_unrecognized_short_names(self):
        """Test unrecognized very short names."""
        assert is_name_recognized("А") is False  # Too short
        assert is_name_recognized("X") is False

    def test_unrecognized_non_alphabetic(self):
        """Test unrecognized non-alphabetic names."""
        assert is_name_recognized("123") is False
        assert is_name_recognized("Name123") is False

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

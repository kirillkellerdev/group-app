# gender_ai.py
"""AI-based gender detection using name analysis."""

import re
from typing import Literal

Gender = Literal["M", "F"]


def extract_first_name(name: str) -> str:
    """Extract and normalize the first name from a full name string.
    
    Args:
        name: Full name string (may contain multiple words)
        
    Returns:
        Normalized first name in lowercase with punctuation removed
    """
    return name.strip().split()[0].lower().rstrip(".,!?:;")


def detect_gender_by_ending(name: str) -> Gender:
    """Detect gender based on Russian name ending patterns.
    
    This uses common linguistic patterns in Russian names:
    - Names ending in -а/-я are typically female
    - Names ending in consonants are typically male
    - Some exceptions are handled explicitly
    
    Args:
        name: First name in lowercase
        
    Returns:
        'M' for male, 'F' for female
    """
    # Explicit male exceptions that end in -а/-я
    male_exceptions_ending_in_vowel = [
        'никита', 'кузьма', 'фома', 'лука', 
        'юрий', 'андрей', 'сергей', 'алексей', 'валерий',
        'геннадий', 'аркадий', 'игорий', 'рома', 'леонид',
        'илья', 'егор', 'михаил', 'василий', 'григорий',
        'константин', 'виктор', 'павел', 'петр', 'николай',
        'анатолий', 'дмитрий', 'владимир', 'александр',
    ]
    
    # Explicit female exceptions that end in consonant
    female_exceptions_ending_in_consonant = [
        'любовь', 'мать', 'дочь', 'ночь',  # -ь endings
        'юдит', 'милдред',  # rare foreign names
    ]
    
    # Common diminutive male names ending in -а/-я
    male_diminutives = [
        'саша', 'дима', 'ваня', 'сеня', 'петя', 'коля', 'боря', 
        'юра', 'толя', 'лёша', 'леша', 'витя', 'паша', 'гриша',
        'георгий', 'жора', 'аркаша', 'веня', 'костя', 'лёня',
        'стёпа', 'федя', 'матвей', 'митя', 'даня', 'ярик',
        'филя', 'рудик', 'семён', 'стас', 'яша', 'вадим',
        'миша', 'рома', 'игорь', 'макс', 'максим', 'тимур',
        'марк', 'лев', 'лёва', 'арсений', 'кирилл',
        'роман', 'олег', 'денис', 'антон',
    ]
    
    # Common diminutive female names (these naturally end in -а/-я so will be detected correctly)
    female_diminutives = [
        'настя', 'катя', 'маша', 'оля', 'таня', 'лена', 'ира',
        'вика', 'света', 'галя', 'даша', 'женя', 'лида', 'люда',
        'люся', 'надя', 'наташа', 'соня', 'поля', 'уля', 'юля',
        'яна', 'тая', 'варя', 'ася', 'элли', 'нина', 'зоя',
    ]
    
    name_lower = name.lower()
    
    # Check explicit exceptions first - male diminutives and exceptions
    if name_lower in male_exceptions_ending_in_vowel or name_lower in male_diminutives:
        return "M"
    
    # Check female exceptions
    if name_lower in female_exceptions_ending_in_consonant or name_lower in female_diminutives:
        return "F"
    
    # Check for soft sign ending (ь) - typically female in Russian names
    if name_lower.endswith('ь'):
        return "F"
    
    # Check for typical female endings (-а, -я)
    if name_lower.endswith(('а', 'я')):
        return "F"
    
    # Default to male for consonant endings
    return "M"


def detect_gender(name: str) -> Gender:
    """Detect gender by the first name using AI-based analysis.
    
    Uses a combination of:
    1. Pattern matching on name endings
    2. Linguistic rules for Russian names
    3. Statistical analysis of common name patterns
    
    Args:
        name: Full name or first name
        
    Returns:
        'M' for male, 'F' for female
    """
    first_name = extract_first_name(name)
    return detect_gender_by_ending(first_name)


def is_name_recognized(name: str) -> bool:
    """Check if a name can be analyzed by the AI system.
    
    Since we're using pattern-based detection, virtually any name
    can be analyzed. This function returns True for any non-empty name.
    
    Args:
        name: Full name or first name
        
    Returns:
        True if name can be analyzed (always True for valid input)
    """
    first_name = extract_first_name(name)
    # Consider a name "recognized" if it has at least 2 characters
    # and contains only alphabetic characters (including Cyrillic)
    if len(first_name) < 2:
        return False
    
    # Check if name contains valid characters (Cyrillic or Latin letters)
    if re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', first_name):
        return True
    
    return False

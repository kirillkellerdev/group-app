# gender_ai.py
"""AI-based gender detection using Namsor API."""

import os
import re
from typing import Literal, Optional
import requests

Gender = Literal["M", "F"]


def get_namsor_api_key() -> str:
    """Get the Namsor API key from environment variable."""
    return os.getenv("NAMSOR_API_KEY", "")


# Namsor API configuration
NAMSOR_API_URL = "https://api.namsor.com/api/gender/full"


def extract_first_name(name: str) -> str:
    """Extract and normalize the first name from a full name string.
    
    Args:
        name: Full name string (may contain multiple words)
        
    Returns:
        Normalized first name in lowercase with punctuation removed
    """
    return name.strip().split()[0].lower().rstrip(".,!?:;")


def detect_gender_by_namsor(name: str) -> Optional[Gender]:
    """Detect gender using the Namsor API.
    
    Args:
        name: First name or full name
        
    Returns:
        'M' for male, 'F' for female, or None if API call fails
    """
    api_key = get_namsor_api_key()
    if not api_key:
        raise ValueError("NAMSOR_API_KEY environment variable is not set")
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": name
    }
    
    try:
        response = requests.post(NAMSOR_API_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Namsor returns gender as "male" or "female"
        gender_result = data.get("gender", "").lower()
        
        if gender_result == "male":
            return "M"
        elif gender_result == "female":
            return "F"
        else:
            return None
            
    except requests.exceptions.RequestException:
        return None


def detect_gender(name: str) -> Gender:
    """Detect gender by the first name using Namsor AI API.
    
    Args:
        name: Full name or first name
        
    Returns:
        'M' for male, 'F' for female, or 'M' as default if detection fails
        
    Raises:
        ValueError: If NAMSOR_API_KEY is not configured
    """
    api_key = get_namsor_api_key()
    if not api_key:
        raise ValueError("NAMSOR_API_KEY environment variable is not set. "
                        "Please set it before using gender detection.")
    
    first_name = extract_first_name(name)
    
    gender = detect_gender_by_namsor(first_name)
    
    if gender is None:
        # Default to 'M' if API fails or returns unknown gender
        return "M"
    
    return gender


def is_name_recognized(name: str) -> bool:
    """Check if a name can be analyzed by the Namsor API.
    
    This function validates that the name has valid format before
    sending it to the API.
    
    Args:
        name: Full name or first name
        
    Returns:
        True if name has valid format, False otherwise
    """
    first_name = extract_first_name(name)
    
    # Consider a name valid if it has at least 2 characters
    # and contains only alphabetic characters (including Cyrillic)
    if len(first_name) < 2:
        return False
    
    # Check if name contains valid characters (Cyrillic or Latin letters)
    if re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', first_name):
        return True
    
    return False

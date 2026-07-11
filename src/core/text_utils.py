"""
Text normalization helpers for OCR output.

OCR (especially on game HUDs) regularly:
  - Drops punctuation: "trashmaster.exe" → "trashmaster exe" or "trashmaster exe"
  - Substitutes characters: "l" ↔ "1", "O" ↔ "0", "|" ↔ "I"
  - Adds/removes spaces

Normalize both the OCR result and the configured value before comparing.
"""

import re


def normalize(text: str) -> str:
    """
    Lowercase, strip punctuation/symbols, collapse whitespace.
    "TrashMaster.exe" → "trashmaster exe"
    "trash|Master_exe" → "trash master exe"
    """
    text = text.lower()
    # Replace common OCR substitutions
    text = text.replace("|", "i").replace("0", "o").replace("1", "l")
    # Replace any non-alphanumeric character with a space
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def names_match(ocr_text: str, configured_name: str, threshold: float = 0.75) -> bool:
    """
    Return True if ocr_text contains a token that is close enough to configured_name.

    First tries exact normalized match.
    Falls back to substring match (OCR may read "trashmaster" without the ".exe" suffix).
    Then tries a simple character overlap ratio for fuzzy matching.
    """
    if not configured_name:
        return False

    norm_ocr  = normalize(ocr_text)
    norm_name = normalize(configured_name)

    # Exact or substring match (most common case)
    if norm_name in norm_ocr:
        return True

    # Check each word in OCR output against each word in the name
    ocr_tokens  = set(norm_ocr.split())
    name_tokens = set(norm_name.split())
    # All name tokens appear somewhere in the OCR text
    if name_tokens and name_tokens.issubset(ocr_tokens):
        return True

    # Fuzzy: longest common substring ratio per name token
    for nt in name_tokens:
        if len(nt) < 4:
            continue
        for ot in ocr_tokens:
            if _similarity(nt, ot) >= threshold:
                return True

    return False


def _similarity(a: str, b: str) -> float:
    """Simple character-level Jaccard similarity."""
    if not a or not b:
        return 0.0
    set_a, set_b = set(a), set(b)
    return len(set_a & set_b) / len(set_a | set_b)

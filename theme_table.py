"""Chart pack theme lookups — ascendant × mahadasha lord themes."""

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

DASHA_LORDS = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter",
    "Venus", "Saturn", "Rahu", "Ketu",
]

MD_THEMES = {
    "Sun": "The soul steps into its authority",
    "Moon": "The heart learns what it truly needs",
    "Mars": "Energy seeks its right direction",
    "Mercury": "The mind sharpens its true purpose",
    "Jupiter": "Wisdom expands into new territory",
    "Venus": "Beauty and harmony take centre stage",
    "Saturn": "The great teacher demands accountability",
    "Rahu": "Ambition meets the unknown",
    "Ketu": "The past releases what no longer serves",
}

THEMES = {
    (sign, lord): "Theme coming soon"
    for sign in SIGNS
    for lord in DASHA_LORDS
}

# Example entries for reference — Ankush will fill the rest
THEMES[("Taurus", "Saturn")] = "The Builder Who Must First Dissolve"
THEMES[("Taurus", "Jupiter")] = "Expansion Finds Its Ground"


def get_theme(ascendant_sign: str, mahadasha_lord: str) -> str:
    return THEMES.get(
        (ascendant_sign, mahadasha_lord),
        "Theme coming soon",
    )


def get_md_theme(mahadasha_lord: str) -> str:
    return MD_THEMES.get(mahadasha_lord, "Your current planetary chapter unfolds.")

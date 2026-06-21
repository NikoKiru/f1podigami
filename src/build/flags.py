"""Country name -> inline SVG flag for the next-race box.

Emoji flags don't render on Windows browsers (they show the country letters),
so we inline a small public-domain SVG flag instead. Only the single next-race
country's flag is embedded per build, so the page stays self-contained with no
external requests. Flags live in data/flags/<iso>.svg (from lipis/flag-icons).

Ergast/Jolpica uses a few non-ISO country names ("UK", "USA", "UAE"), mapped
here to ISO 3166-1 alpha-2. Unknown country -> "".
"""

from __future__ import annotations

from pathlib import Path

_FLAG_DIR = Path(__file__).resolve().parents[2] / "data" / "flags"

COUNTRY_ISO: dict[str, str] = {
    "Australia": "AU",
    "Austria": "AT",
    "Azerbaijan": "AZ",
    "Bahrain": "BH",
    "Belgium": "BE",
    "Brazil": "BR",
    "Canada": "CA",
    "China": "CN",
    "France": "FR",
    "Germany": "DE",
    "Hungary": "HU",
    "India": "IN",
    "Italy": "IT",
    "Japan": "JP",
    "Korea": "KR",
    "Malaysia": "MY",
    "Mexico": "MX",
    "Monaco": "MC",
    "Netherlands": "NL",
    "Portugal": "PT",
    "Qatar": "QA",
    "Russia": "RU",
    "Saudi Arabia": "SA",
    "Singapore": "SG",
    "South Africa": "ZA",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Turkey": "TR",
    "UAE": "AE",
    "United Arab Emirates": "AE",
    "UK": "GB",
    "United Kingdom": "GB",
    "United States": "US",
    "USA": "US",
}


def iso_code(country: str) -> str:
    """ISO 3166-1 alpha-2 for a country name, or "" if unknown."""
    return COUNTRY_ISO.get(country, "")


def flag_svg(country: str) -> str:
    """Inline SVG flag markup (class="nr-flag") for a country, or "" if missing."""
    iso = COUNTRY_ISO.get(country, "")
    if len(iso) != 2:
        return ""
    path = _FLAG_DIR / f"{iso.lower()}.svg"
    if not path.exists():
        return ""
    svg = path.read_text(encoding="utf-8").strip()
    if svg.startswith("<svg") and "nr-flag" not in svg[:80]:
        svg = svg.replace("<svg", '<svg class="nr-flag"', 1)
    return svg

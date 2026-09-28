"""Classify OpenStreetMap tags into the destination categories of the atlas.

The rules are simple and documented in METHODOLOGY.md. Where OSM tagging is ambiguous,
they err on the side of *more* destinations, so that reported accessibility gaps are
conservative: the real situation is at least as bad as shown.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

CATEGORIES: dict[str, str] = {
    "gp": "Hausarzt",
    "pharmacy": "Apotheke",
    "supermarket": "Supermarkt",
    "primary_school": "Grundschule",
    "secondary_school": "Weiterführende Schule",
    "hospital": "Krankenhaus",
    "rail_station": "Bahnhof",
}

GP_SPECIALITIES = frozenset(
    {
        "general",
        "general_practice",
        "general_practitioner",
        "allgemeinmedizin",
        "family_medicine",
        "family_practice",
    }
)
# Many internists work as family doctors in Germany ("hausaerztliche Internisten").
GP_LENIENT_SPECIALITIES = frozenset({"internal", "internal_medicine", "innere_medizin"})

_NOT_A_GP_NAME = re.compile(r"zahn|kieferorthop|tierarzt|tierärzt|tierklinik|\bkfo\b")
_GP_NAME = re.compile(r"allgemeinmedizin|hausarzt|hausärzt|praktische[rn]? ärzt|praktischer arzt")

_PRIMARY = re.compile(r"grundschule|grund-\s*und|volksschule|primarschule|\bprimary\b")
_SECONDARY = re.compile(
    r"gymnasium|gemeinschaftsschule|realschule|gesamtschule|oberschule|hauptschule|"
    r"mittelschule|sekundarschule|regionalschule|stadtteilschule|werkrealschule|\bsecondary\b"
)
_NOT_GENERAL_SCHOOL = re.compile(
    r"berufs|\bbbz\b|fachschule|fachoberschule|hochschule|universit|musikschule|fahrschule|"
    r"tanzschule|volkshochschule|sprachschule|förderschule|foerderschule|förderzentrum|"
    r"sonderschule|kindergarten|\bkita\b|abendschule|kolleg\b|akademie|nachhilfe|"
    r"jagdschule|reitschule|hundeschule|kochschule|pflegeschule|ausbildung|lebenshilfe|"
    r"waldklassenzimmer|waldschulprojekt|kurswerkstatt|kulturzentrum|landesinstitut|"
    r"technikum|für wirtschaft|schulhof|\btrakt\b|ehemalig|école|ecole|lycée|collège"
)
# Many primary schools in Saarland carry only a name such as "Aschbachschule".
_GENERIC_SCHOOL_NAME = re.compile(r"schule\b")
_SCHOOL_TEXT_KEYS = ("name", "official_name", "short_name", "school", "school:de", "school:type")

_HOSPITAL_EXCLUDE = re.compile(
    r"reha|tagesklinik|psychiatr|psychosomat|hospiz|pflegeheim|seniorenheim|kurklinik|"
    r"suchtklinik|forensi|tierklinik"
)
_SPECIALISED_ONLY = frozenset(
    {"psychiatry", "child_psychiatry", "psychotherapy", "psychosomatics", "rehabilitation"}
)


def _values(tags: Mapping[str, str], key: str) -> set[str]:
    return {part.strip().lower() for part in re.split(r"[;,]", tags.get(key, "")) if part.strip()}


def gp_variant(tags: Mapping[str, str]) -> str | None:
    """``"strict"`` for clearly tagged family doctors, ``"lenient"`` for plausible ones."""
    if tags.get("amenity") != "doctors" and tags.get("healthcare") != "doctor":
        return None
    name = tags.get("name", "").lower()
    if _NOT_A_GP_NAME.search(name):
        return None
    specialities = _values(tags, "healthcare:speciality")
    if specialities & GP_SPECIALITIES or _GP_NAME.search(name):
        return "strict"
    if not specialities or specialities & GP_LENIENT_SPECIALITIES:
        return "lenient"
    return None


def school_levels(tags: Mapping[str, str]) -> dict[str, bool]:
    """``{level: is_strict}`` for general-education schools.

    ``is_strict`` is False for schools that only count as primary schools because of a
    generic name without any other hint.
    """
    if tags.get("amenity") != "school":
        return {}
    text = " ".join(tags.get(key, "") for key in _SCHOOL_TEXT_KEYS).lower()
    named_primary = bool(_PRIMARY.search(text))
    named_secondary = bool(_SECONDARY.search(text))
    if _NOT_GENERAL_SCHOOL.search(text) and not (named_primary or named_secondary):
        return {}
    isced = set(re.findall(r"\d", tags.get("isced:level", "")))
    grades = [int(value) for value in re.findall(r"\d+", tags.get("grades", ""))]
    levels: dict[str, bool] = {}
    if named_primary or "1" in isced or (grades and min(grades) <= 4):
        levels["primary_school"] = True
    if named_secondary or isced & {"2", "3"} or (grades and max(grades) >= 5):
        levels["secondary_school"] = True
    if not levels and _GENERIC_SCHOOL_NAME.search(tags.get("name", "").lower()):
        levels["primary_school"] = False
    return levels


def is_hospital(tags: Mapping[str, str]) -> bool:
    """General hospitals. Purely psychiatric, rehabilitation and day clinics without an
    emergency department are excluded, as are former hospitals."""
    if tags.get("amenity") != "hospital" and tags.get("healthcare") != "hospital":
        return False
    name = tags.get("name", "").lower()
    if "ehemalig" in name:
        return False
    if tags.get("emergency") == "yes":
        return True
    if _HOSPITAL_EXCLUDE.search(name):
        return False
    specialities = _values(tags, "healthcare:speciality")
    return not (specialities and specialities <= _SPECIALISED_ONLY)


def classify(tags: Mapping[str, str]) -> dict[str, bool]:
    """Map an OSM object's tags to ``{category: is_strict}``; empty if not a destination."""
    result: dict[str, bool] = {}
    variant = gp_variant(tags)
    if variant is not None:
        result["gp"] = variant == "strict"
    if tags.get("amenity") == "pharmacy" or tags.get("healthcare") == "pharmacy":
        result["pharmacy"] = True
    if tags.get("shop") == "supermarket":
        result["supermarket"] = True
    for level, strict in sorted(school_levels(tags).items()):
        result[level] = strict
    if is_hospital(tags):
        result["hospital"] = True
    return result

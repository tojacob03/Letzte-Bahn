from __future__ import annotations

import pytest

from transit_atlas.pois import classify

DOCTOR = {"amenity": "doctors"}
SCHOOL = {"amenity": "school"}


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({**DOCTOR, "healthcare:speciality": "general"}, {"gp": True}),
        ({**DOCTOR, "name": "Praxis für Allgemeinmedizin Dr. Muster"}, {"gp": True}),
        (DOCTOR, {"gp": False}),
        ({**DOCTOR, "healthcare:speciality": "internal"}, {"gp": False}),
        ({**DOCTOR, "healthcare:speciality": "ophthalmology"}, {}),
        ({**DOCTOR, "name": "Zahnarztpraxis Muster"}, {}),
        ({"amenity": "dentist"}, {}),
        ({"amenity": "pharmacy", "name": "Löwen-Apotheke"}, {"pharmacy": True}),
        ({"healthcare": "pharmacy"}, {"pharmacy": True}),
        ({"shop": "supermarket"}, {"supermarket": True}),
        ({"shop": "convenience"}, {}),
    ],
)
def test_health_and_shopping(tags, expected):
    assert classify(tags) == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({**SCHOOL, "name": "Grundschule Am Park"}, {"primary_school": True}),
        ({**SCHOOL, "name": "Gemeinschaftsschule Lebach"}, {"secondary_school": True}),
        (
            {**SCHOOL, "name": "Grund- und Gemeinschaftsschule"},
            {"primary_school": True, "secondary_school": True},
        ),
        ({**SCHOOL, "isced:level": "1"}, {"primary_school": True}),
        ({**SCHOOL, "name": "Gymnasium am Rotenbühl"}, {"secondary_school": True}),
        ({**SCHOOL, "name": "Berufsbildungszentrum Saarlouis", "isced:level": "3"}, {}),
        ({**SCHOOL, "name": "Förderschule Lernen"}, {}),
        ({**SCHOOL, "name": "Schule am See"}, {}),
    ],
)
def test_schools(tags, expected):
    assert classify(tags) == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"amenity": "hospital", "name": "Klinikum Saarbrücken"}, {"hospital": True}),
        ({"amenity": "hospital", "name": "Reha-Klinik Am Wald"}, {}),
        ({"healthcare": "hospital", "healthcare:speciality": "psychiatry"}, {}),
    ],
)
def test_hospitals(tags, expected):
    assert classify(tags) == expected

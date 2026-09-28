from __future__ import annotations

import pytest

from transit_atlas.pois import classify

DOCTOR = {"amenity": "doctors"}
SCHOOL = {"amenity": "school"}
HOSPITAL = {"amenity": "hospital", "healthcare": "hospital"}


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
        ({**SCHOOL, "grades": "5-10"}, {"secondary_school": True}),
        ({**SCHOOL, "name": "Gymnasium am Rotenbühl"}, {"secondary_school": True}),
        # generic names are mostly primary schools in Saarland, flagged as not strict
        ({**SCHOOL, "name": "Aschbachschule"}, {"primary_school": False}),
        ({**SCHOOL, "name": "Schule am See"}, {"primary_school": False}),
        ({**SCHOOL, "name": "Berufsbildungszentrum Saarlouis", "isced:level": "3"}, {}),
        ({**SCHOOL, "name": "Förderschule Lernen"}, {}),
        ({**SCHOOL, "name": "Jagdschule Blatt"}, {}),
        ({**SCHOOL, "name": "Waldklassenzimmer"}, {}),
        ({**SCHOOL, "building": "yes"}, {}),
    ],
)
def test_schools(tags, expected):
    assert classify(tags) == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({**HOSPITAL, "name": "Klinikum Saarbrücken"}, {"hospital": True}),
        ({**HOSPITAL, "name": "Reha-Klinik Am Wald"}, {}),
        ({**HOSPITAL, "healthcare:speciality": "psychiatry"}, {}),
        # a general hospital with a psychiatric ward and an emergency department counts
        (
            {**HOSPITAL, "name": "Marienkrankenhaus Sankt Wendel", "emergency": "yes",
             "healthcare:speciality": "geriatrics;psychiatry"},
            {"hospital": True},
        ),
        ({**HOSPITAL, "name": "ehemalige Knappschaftsklinik Quierschied"}, {}),
    ],
)
def test_hospitals(tags, expected):
    assert classify(tags) == expected

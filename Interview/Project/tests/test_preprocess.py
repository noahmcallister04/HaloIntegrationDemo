import pytest

from middleware.preprocess import Normalizer, clean_text
from settings import resolve_path


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    return Normalizer.from_file(resolve_path("synonyms.yaml"), fuzzy_threshold=90)


def test_strips_email_junk():
    text = (
        "CAUTION: This email originated from outside of the organization. Do not click links.\n\n"
        "Hi team,\n\n"
        "The copier at Station 4 wont print.\n\n"
        "Thanks,\nCapt. Jim Reyes\nFirefighter/EMT | Riverside Fire Dept\n(555) 201-3344\n\n"
        "Sent from my iPhone"
    )
    assert clean_text(text) == "the copier at station 4 won't print."


def test_keeps_forwarded_body_but_drops_headers():
    text = (
        "FYI see below\n\n"
        "From: Dana Halvorsen <dana.halvorsen@riversidefire.example>\n"
        "Sent: Monday, March 2, 2026 8:14 AM\n"
        "To: Help Desk <help@msp.example>\n"
        "Subject: RE: cad down\n\n"
        "CAD is down on Medic 3"
    )
    assert clean_text(text) == "fyi see below cad down cad is down on medic 3"


def test_greeting_word_inside_real_text_is_kept():
    assert clean_text("hi printer broken") == "hi printer broken"


def test_synonyms_map_device_names(normalizer):
    p = normalizer.process("truck laptop wont connect to dispatch again")
    assert p.normalized_text == "toughbook won't connect to cad again"
    assert p.concepts == {"toughbook", "cad"}


@pytest.mark.parametrize("text", ["CF-33 is dead", "tuffbook is dead", "toughbok is dead", "cf33 is dead"])
def test_toughbook_variants_and_typos(normalizer, text):
    assert normalizer.process(text).normalized_text == "toughbook is dead"


def test_longest_phrase_wins(normalizer):
    p = normalizer.process("computer aided dispatch is slow")
    assert p.normalized_text == "cad is slow"


def test_phrase_concepts_use_spaces(normalizer):
    p = normalizer.process("I'm locked out and the tones didn't drop")
    assert p.concepts == {"account_access", "station_alerting"}
    assert "account access" in p.normalized_text
    assert "station alerting" in p.normalized_text


def test_unrelated_words_not_fuzzed(normalizer):
    # "printed" is close to "printer" but below the threshold.
    assert normalizer.process("it printed blank pages").normalized_text == "it printed blank pages"

from src.core.slugging import slug_candidate, slugify


def test_slugify_normalizes_human_names():
    assert slugify("Housing Prices v2") == "housing-prices-v2"


def test_slugify_falls_back_when_value_has_no_ascii_word_characters():
    assert slugify("!!!") == "resource"


def test_slug_candidate_uses_suffix_for_collisions():
    assert slug_candidate("dataset", 1) == "dataset"
    assert slug_candidate("dataset", 3) == "dataset-3"

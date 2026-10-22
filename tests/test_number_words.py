from utils import (amount_to_words_parts, number_to_text, places_to_text,
                   calculate_total_places_text_master)


def test_amount_words_above_999():
    assert amount_to_words_parts(1000)[0] == "одна тысяча"
    assert amount_to_words_parts(1200)[0] == "одна тысяча двести"
    assert amount_to_words_parts(2102)[0] == "две тысячи сто два"
    assert amount_to_words_parts(12345.67) == (
        "двенадцать тысяч триста сорок пять", "67")
    assert amount_to_words_parts(1_200_000)[0] == "один миллион двести тысяч"


def test_number_to_text_scales():
    assert number_to_text(1000) == "одна тысяча"
    assert number_to_text(21000) == "двадцать одна тысяча"
    assert number_to_text(1000000) == "один миллион"
    assert number_to_text("20.5") == "двадцать целых пять десятых"


def test_places_above_ten():
    assert places_to_text("11") == "одиннадцать"
    assert places_to_text("21") == "двадцать одно"
    assert places_to_text("101") == "сто одно"
    assert calculate_total_places_text_master(
        [{"places": "11"}, {"places": "10"}]) == "двадцать одно"

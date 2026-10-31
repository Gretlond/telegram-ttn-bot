import utils
import word_filler


def test_explicit_places_win_over_tipper_fallback():
    cargo = {'places': '3', 'trips': '2'}

    assert utils.cargo_places_value(cargo) == '3'
    assert word_filler.cargo_places_value(cargo) == '3'


def test_tipper_without_places_prints_nav():
    cargo = {'places': '', 'trips': '2'}

    assert utils.cargo_places_value(cargo) == 'нав.'
    assert word_filler.cargo_places_value(cargo) == 'нав.'


def test_regular_cargo_without_places_stays_empty():
    assert utils.cargo_places_value({'places': '', 'trips': ''}) == ''
    assert utils.cargo_places_value({}) == ''
    assert word_filler.cargo_places_value({}) == ''


def test_total_places_text_uses_naval_for_tipper():
    cargos = [{'places': '', 'trips': '3'}]

    assert utils.calculate_total_places_text_master(cargos) == 'навал'


def test_total_places_text_uses_naval_when_mixed():
    cargos = [{'places': '2'}, {'places': '', 'trips': '1'}]

    assert utils.calculate_total_places_text_master(cargos) == 'навал'

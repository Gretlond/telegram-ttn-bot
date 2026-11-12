import json

import config
import utils


def test_load_masters_skips_invalid_ids(tmp_path, monkeypatch):
    masters_file = tmp_path / "masters.json"
    masters_file.write_text(json.dumps({
        "0": {"name": "Битый", "locations": ["loc_1"]},
        "-5": {"name": "Отрицательный", "locations": ["loc_1"]},
        "abc": {"name": "Нечисловой", "locations": ["loc_1"]},
        "500": {"name": "Мастер", "locations": ["loc_1"]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "MASTERS_FILE", str(masters_file))
    monkeypatch.setattr(config, "YOUR_TELEGRAM_ID", 900)
    monkeypatch.setattr(config, "MASTERS", {})

    config.load_masters()

    assert set(config.MASTERS) == {500, 900}
    saved = json.loads(masters_file.read_text(encoding="utf-8"))
    assert set(saved) == {"500", "900"}


def test_load_masters_does_not_create_admin_for_zero(tmp_path, monkeypatch):
    masters_file = tmp_path / "masters.json"
    masters_file.write_text(json.dumps({
        "0": {"name": "Битый", "locations": ["loc_1"]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(config, "MASTERS_FILE", str(masters_file))
    monkeypatch.setattr(config, "YOUR_TELEGRAM_ID", 0)
    monkeypatch.setattr(config, "MASTERS", {})

    config.load_masters()

    assert config.MASTERS == {}
    saved = json.loads(masters_file.read_text(encoding="utf-8"))
    assert saved == {}


def _set_masters(monkeypatch, masters, admin_id):
    monkeypatch.setattr(utils, "MASTERS", masters)
    monkeypatch.setattr(utils, "LOCATIONS", {
        "loc_1": {"name": "Склад", "master": "Мастер"},
        "loc_2": {"name": "Объект", "master": "Мастер"},
    })
    monkeypatch.setattr(utils, "YOUR_TELEGRAM_ID", admin_id)


def test_find_masters_ignores_zero_and_negative(monkeypatch):
    _set_masters(monkeypatch, {
        "0": {"name": "Битый", "locations": ["loc_1"]},
        "-7": {"name": "Отрицательный", "locations": ["loc_1"]},
        "500": {"name": "Мастер", "locations": ["loc_1"]},
    }, admin_id=900)

    assert utils.find_masters_by_loading("Склад") == [500]


def test_find_masters_removes_duplicates(monkeypatch):
    _set_masters(monkeypatch, {
        "500": {"name": "Мастер", "locations": ["loc_1"]},
        " 500": {"name": "Мастер-дубль", "locations": ["loc_1"]},
        "0": {"name": "Битый", "locations": ["loc_1"]},
    }, admin_id=900)

    assert utils.find_masters_by_loading("Склад") == [500]


def test_find_masters_falls_back_to_valid_admin(monkeypatch):
    _set_masters(monkeypatch, {
        "0": {"name": "Битый", "locations": ["loc_1"]},
    }, admin_id=900)

    assert utils.find_masters_by_loading("Склад") == [900]


def test_find_masters_returns_nothing_without_valid_admin(monkeypatch):
    _set_masters(monkeypatch, {
        "0": {"name": "Битый", "locations": ["loc_1"]},
    }, admin_id=0)

    assert utils.find_masters_by_loading("Склад") == []

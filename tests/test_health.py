import sqlite3
from types import SimpleNamespace

import pytest

import health
import orders_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_health.db"))
    orders_db.init_db()
    return orders_db


def _order_data():
    return {
        "day": "22", "month": "10", "year": "26",
        "waybill_number": "WB-1", "car_model": "МАЗ",
        "car_plate": "1234 AB", "trailer_info": "-",
        "loading_point": "Склад", "unloading_point": "Объект",
        "driver_name": "Водитель",
        "cargos": [{"cargo_name": "Груз", "cargo_qty": "10"}],
    }


class FakeBot:
    def __init__(self):
        self.calls = []

    def get_chat(self, master_id):
        self.calls.append(master_id)
        if int(master_id) == 500:
            return SimpleNamespace(first_name="Иван", username="ivan")
        raise RuntimeError("chat not found")


def test_master_health_checks_chat_and_locations():
    checks = health.check_masters(
        FakeBot(),
        {
            "500": {"name": "Иван", "locations": ["loc_1"]},
            "600": {"name": "Пётр", "locations": ["loc_2"]},
        },
        {"loc_1": {"name": "Склад"}, "loc_2": {"name": "Объект"}},
    )

    assert checks[0]["id"] == 500
    assert checks[0]["ok"] is True
    assert checks[0]["locations"] == ["Склад"]
    assert checks[1]["ok"] is False
    assert "chat not found" in checks[1]["error"]


def test_last_backup_reports_valid_copy(tmp_path):
    target = tmp_path / "backup" / "2026-10-29"
    target.mkdir(parents=True)
    conn = sqlite3.connect(target / "orders.db")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    result = health.get_last_backup(str(tmp_path / "backup"))

    assert result is not None
    assert result["path"].endswith("2026-10-29")
    assert result["errors"] == []
    assert result["age_hours"] >= 0


def test_backup_monitor_reports_timer_and_missing_copy(tmp_path):
    monitor = health.get_backup_monitor(
        backup_dir=str(tmp_path / "missing"), timer_status="inactive")

    assert monitor["timer_status"] == "inactive"
    assert monitor["backup"] is None
    assert any("таймер" in issue for issue in monitor["issues"])
    assert any("не найдена" in issue for issue in monitor["issues"])
    assert "Мониторинг резервных копий" in (
        health.get_backup_alert(
            backup_dir=str(tmp_path / "missing"), timer_status="inactive"))


def test_backup_monitor_is_clean_when_timer_and_copy_ok(tmp_path):
    target = tmp_path / "backup" / "2026-10-30"
    target.mkdir(parents=True)
    conn = sqlite3.connect(target / "orders.db")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monitor = health.get_backup_monitor(
        backup_dir=str(tmp_path / "backup"), timer_status="active")

    assert monitor["issues"] == []
    assert health.get_backup_alert(
        backup_dir=str(tmp_path / "backup"), timer_status="active") is None


def test_status_text_includes_delivery_problem_and_masters(
    temp_db, tmp_path
):
    order_id = temp_db.save_order(_order_data(), master_id=500, driver_id=900)
    temp_db.mark_order_delivery(order_id, "failed", "chat not found")
    checks = [{
        "id": 500, "name": "Иван", "locations": ["Склад"],
        "ok": True, "error": "", "chat_name": "Иван", "username": "ivan",
    }]

    text = health.build_status_text(
        checks, db_file=temp_db.DB_FILE, backup_dir=str(tmp_path / "none")
    )

    assert "Состояние бота" in text
    assert "ошибки 1" in text
    assert f"№{order_id}" in text
    assert "✅ 500" in text
    assert "Последний бэкап: не найден" in text

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import orders_db
from utils import delivery_status_ru


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_delivery.db"))
    orders_db.init_db()
    return orders_db


def _order_data(number=1):
    return {
        "day": "22", "month": "10", "year": "26",
        "waybill_number": f"WB-{number}",
        "car_model": "МАЗ", "car_plate": f"1234 AB-{number}",
        "trailer_info": "-", "loading_point": "Склад",
        "unloading_point": "Объект", "driver_name": "Водитель",
        "cargos": [{"cargo_name": "Груз", "cargo_qty": "10"}],
    }


def test_new_order_is_pending_delivery(temp_db):
    order_id = temp_db.save_order(_order_data(), master_id=500, driver_id=900)

    order = temp_db.get_order(order_id)
    assert order["delivery_status"] == "pending"
    assert order["delivery_error"] is None
    assert order["delivered_at"] is None


def test_delivery_status_is_recorded_and_listed(temp_db):
    first = temp_db.save_order(_order_data(1), master_id=500, driver_id=900)
    second = temp_db.save_order(_order_data(2), master_id=500, driver_id=901)

    assert temp_db.mark_order_delivery(first, "delivered") is True
    assert temp_db.mark_order_delivery(second, "failed", "chat not found") is True

    delivered = temp_db.get_order(first)
    failed = temp_db.get_order(second)
    assert delivered["delivery_status"] == "delivered"
    assert delivered["delivered_at"]
    assert delivered["delivery_error"] is None
    assert failed["delivery_status"] == "failed"
    assert failed["delivery_error"] == "chat not found"
    assert failed["delivered_at"] is None

    undelivered = temp_db.get_undelivered_orders()
    assert [order["id"] for order in undelivered] == [second]
    assert temp_db.get_delivery_counts() == {
        "delivered": 1,
        "failed": 1,
    }


def test_delivery_status_is_readable_in_ui():
    assert "доставлено" in delivery_status_ru("delivered")
    assert "не доставлено" in delivery_status_ru("failed")
    assert "ожидает" in delivery_status_ru("pending")
    assert delivery_status_ru("unknown") == "—"


def test_legacy_database_migrates_to_unknown_then_pending(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER, driver_id INTEGER, driver_name TEXT,
            waybill_number TEXT, date TEXT, car_model TEXT, car_plate TEXT,
            trailer_info TEXT, loading_point TEXT, unloading_point TEXT,
            shipper_handed_by TEXT, consignee_received_by TEXT,
            release_allowed_by TEXT, cargo_accepted_by TEXT,
            cargo_json TEXT, status TEXT DEFAULT 'new', created_at TEXT,
            master_message_id INTEGER, deleted_at TEXT
        )
    """)
    conn.execute("INSERT INTO orders (master_id, waybill_number) VALUES (500, 'OLD-1')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(orders_db, "DB_FILE", str(db_path))

    orders_db.init_db()

    legacy = orders_db.get_order(1)
    assert legacy["delivery_status"] == "unknown"
    new_id = orders_db.save_order(
        _order_data(2), master_id=500, driver_id=900)
    assert orders_db.get_order(new_id)["delivery_status"] == "pending"


def test_invalid_delivery_status_rejected(temp_db):
    order_id = temp_db.save_order(_order_data(), master_id=500, driver_id=900)

    with pytest.raises(ValueError):
        temp_db.mark_order_delivery(order_id, "sent")


class FakeApi:
    def __init__(self):
        self.messages = []
        self.documents = []

    def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))
        return SimpleNamespace(message_id=1)

    def send_document(self, chat_id, document, **kwargs):
        self.documents.append((chat_id, getattr(document, "name", "")))


def test_resend_order_to_master_marks_delivered(temp_db, tmp_path, monkeypatch):
    import driver_order_summary

    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)

    def rebuild(order_id, output_dir=None):
        path = Path(output_dir) / "order.docx"
        path.write_bytes(b"doc")
        return str(path)

    monkeypatch.setattr(
        driver_order_summary, "_rebuild_order_document", rebuild)
    api = FakeApi()

    result = driver_order_summary.resend_order_to_master(
        order_id, bot_api=api)

    assert result == order_id
    assert temp_db.get_order(order_id)["delivery_status"] == "delivered"
    assert api.messages[0][0] == 500
    assert api.documents and api.documents[0][0] == 500


def test_resend_order_skips_already_delivered(temp_db, monkeypatch):
    import driver_order_summary

    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)
    temp_db.mark_order_delivery(order_id, "delivered")

    def rebuild(order_id, output_dir=None):
        raise AssertionError("delivered order must not be resent")

    monkeypatch.setattr(
        driver_order_summary, "_rebuild_order_document", rebuild)

    result = driver_order_summary.resend_order_to_master(
        order_id, bot_api=FakeApi())

    assert result == order_id


def test_resend_order_to_master_marks_failure(temp_db, tmp_path, monkeypatch):
    import driver_order_summary

    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)

    def rebuild(order_id, output_dir=None):
        raise RuntimeError("document generation failed")

    monkeypatch.setattr(
        driver_order_summary, "_rebuild_order_document", rebuild)

    with pytest.raises(RuntimeError, match="document generation failed"):
        driver_order_summary.resend_order_to_master(
            order_id, bot_api=FakeApi())

    failed = temp_db.get_order(order_id)
    assert failed["delivery_status"] == "failed"
    assert "document generation failed" in failed["delivery_error"]


def test_retry_undelivered_delivery_reports_partial_success(
    temp_db, monkeypatch
):
    import driver_order_summary

    first = temp_db.save_order(_order_data(1), master_id=500, driver_id=900)
    second = temp_db.save_order(_order_data(2), master_id=500, driver_id=901)

    def rebuild(order_id, output_dir=None):
        if int(order_id) == second:
            raise RuntimeError("second failed")
        from pathlib import Path
        path = Path(output_dir) / "order.docx"
        path.write_bytes(b"doc")
        return str(path)

    monkeypatch.setattr(
        driver_order_summary, "_rebuild_order_document", rebuild)

    result = driver_order_summary.retry_undelivered_delivery(
        bot_api=FakeApi())

    assert result["attempted"] == 2
    assert result["delivered"] == [first]
    assert result["failed"][0]["id"] == second
    assert temp_db.get_order(first)["delivery_status"] == "delivered"
    assert temp_db.get_order(second)["delivery_status"] == "failed"

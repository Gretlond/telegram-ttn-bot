from datetime import date

import pytest

import orders_db
import registry
import registry_filler
import registry_history
import word_filler


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_history.db"))
    orders_db.init_db()
    return orders_db


def _order_data(number=1):
    return {
        "day": "22", "month": "10", "year": "26",
        "waybill_number": f"WB-{number}",
        "car_model": "МАЗ", "car_plate": f"1234 AB-{number}",
        "trailer_info": "-",
        "loading_point": "Склад", "unloading_point": "Объект",
        "driver_name": "Иванов И.И.",
        "cargos": [{
            "cargo_name": "Песок", "cargo_qty": "10",
            "places": "2", "price": "100",
        }],
    }


def _manual(ttn, row, order_date="29.10.26"):
    return {
        "ttn_number": ttn, "date": order_date,
        "loading_point": "Склад", "driver_name": "Петров П.П.",
        "car_plate": "7777 AB", "target_row": row,
    }


def _batch_with_order(temp_db, master_id=500, start="0219200"):
    batch_id = temp_db.create_batch(master_id, start)
    order_id = temp_db.save_order(
        _order_data(1), master_id=master_id, driver_id=900)
    temp_db.assign_orders_to_batch(batch_id, [order_id])
    return batch_id, order_id


def test_build_registry_stats_uses_top_and_bottom_rows():
    orders = [
        {"order_row": 23, "ttn_number": "0219198", "date": "24.10.26"},
        {"order_row": 25, "ttn_number": "0219200", "date": "22.10.26"},
        {"order_row": 24, "ttn_number": "0219199", "date": "29.10.26"},
    ]
    manual = [
        {"target_row": 22, "ttn_number": "0219197", "date": "20.10.26"},
    ]

    stats = registry_history.build_registry_stats(orders, manual)

    assert stats["count"] == 4
    assert stats["first_ttn"] == "0219200"
    assert stats["last_ttn"] == "0219197"
    assert stats["first_date"] == date(2026, 10, 20)
    assert stats["last_date"] == date(2026, 10, 29)


def test_build_registry_stats_without_rows_uses_descending_ttn():
    orders = [
        {"order_row": None, "ttn_number": "0219186", "date": "21.10.26"},
        {"order_row": None, "ttn_number": "0219200", "date": "22.10.26"},
    ]

    stats = registry_history.build_registry_stats(orders, [])

    assert stats["first_ttn"] == "0219200"
    assert stats["last_ttn"] == "0219186"


def test_format_registry_label_contains_ttn_and_date_ranges():
    stats = {
        "count": 4,
        "first_ttn": "0219200",
        "last_ttn": "0219197",
        "first_date": date(2026, 10, 20),
        "last_date": date(2026, 10, 29),
    }

    assert registry_history.format_ttn_range(stats) == "0219200–0219197"
    assert registry_history.format_date_range(stats) == "20.10.26–29.10.26"
    assert registry_history.format_registry_label(7, stats) == (
        "№7 • ТТН 0219200–0219197 • 20.10.26–29.10.26")


def test_parse_registry_date_supports_bot_and_db_formats():
    assert registry_history.parse_registry_date("29.10.26") == date(2026, 10, 29)
    assert registry_history.parse_registry_date("29.10.2026") == date(2026, 10, 29)
    assert registry_history.parse_registry_date("2026-10-29") == date(2026, 10, 29)
    assert registry_history.parse_registry_date("") is None
    assert registry_history.parse_registry_date("мусор") is None


def test_get_closed_batches_returns_only_closed_nonempty(temp_db):
    closed_batch, _ = _batch_with_order(temp_db, start="0219200")
    temp_db.close_batch(closed_batch)

    open_batch, _ = _batch_with_order(temp_db, start="0219000")

    empty_batch = temp_db.create_batch(500, "0218800")
    temp_db.close_batch(empty_batch)

    other_batch, _ = _batch_with_order(
        temp_db, master_id=777, start="0218700")
    temp_db.close_batch(other_batch)

    batches = temp_db.get_closed_batches(500)

    assert [batch["id"] for batch in batches] == [closed_batch]
    assert batches[0]["orders_count"] == 1
    assert batches[0]["manual_count"] == 0
    assert open_batch not in [batch["id"] for batch in batches]


def test_get_closed_batches_includes_manual_only_batch(temp_db):
    batch_id, _ = temp_db.create_batch_with_manual(
        500, "0219200", _manual("0219200", 25))
    temp_db.close_batch(batch_id)

    batches = temp_db.get_closed_batches(500)

    assert [batch["id"] for batch in batches] == [batch_id]
    assert batches[0]["orders_count"] == 0
    assert batches[0]["manual_count"] == 1


def test_archive_registry_copies_files_and_keeps_originals(
    tmp_path, monkeypatch
):
    result = tmp_path / "Результат"
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    source = tmp_path / "source"
    source.mkdir()
    docx = source / "Реестр_ТТН_batch7.docx"
    pdf = source / "Реестр_ТТН_batch7.pdf"
    docx.write_bytes(b"docx-data")
    pdf.write_bytes(b"pdf-data")

    copied = registry_history.archive_registry(7, str(docx), str(pdf))

    target = result / "История_реестров" / "batch_7"
    assert (target / docx.name).read_bytes() == b"docx-data"
    assert (target / pdf.name).read_bytes() == b"pdf-data"
    assert copied == [str(target / docx.name), str(target / pdf.name)]
    assert docx.exists()
    assert pdf.exists()


def test_ensure_history_files_prefers_archive(tmp_path, monkeypatch):
    result = tmp_path / "Результат"
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    target = result / "История_реестров" / "batch_7"
    target.mkdir(parents=True)
    docx = target / "Реестр_ТТН_batch7.docx"
    pdf = target / "Реестр_ТТН_batch7.pdf"
    docx.write_bytes(b"docx-data")
    pdf.write_bytes(b"pdf-data")

    def fail_regenerate(*args, **kwargs):
        raise AssertionError("архивный реестр не должен перегенерироваться")

    monkeypatch.setattr(
        registry_history.batch_registry,
        "regenerate_batch_registry",
        fail_regenerate,
    )

    assert registry_history.ensure_history_files(7) == (str(docx), str(pdf))


def test_ensure_history_files_restores_and_archives_missing_registry(
    tmp_path, monkeypatch
):
    result = tmp_path / "Результат"
    result.mkdir()
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    generated = tmp_path / "generated"
    generated.mkdir()
    docx = generated / "Реестр_ТТН_batch7.docx"
    pdf = generated / "Реестр_ТТН_batch7.pdf"
    docx.write_bytes(b"docx-data")
    pdf.write_bytes(b"pdf-data")
    calls = []

    def fake_regenerate(batch_id, output_name=None):
        calls.append((batch_id, output_name))
        return str(docx), str(pdf)

    monkeypatch.setattr(
        registry_history.batch_registry,
        "regenerate_batch_registry",
        fake_regenerate,
    )

    restored = registry_history.ensure_history_files(7)

    assert restored == (str(docx), str(pdf))
    assert calls == [(7, "Реестр_ТТН_batch7")]
    target = result / "История_реестров" / "batch_7"
    assert (target / docx.name).exists()
    assert (target / pdf.name).exists()


def test_ensure_history_files_creates_missing_pdf(tmp_path, monkeypatch):
    result = tmp_path / "Результат"
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    target = result / "История_реестров" / "batch_7"
    target.mkdir(parents=True)
    docx = target / "Реестр_ТТН_batch7.docx"
    docx.write_bytes(b"docx-data")
    pdf = target / "Реестр_ТТН_batch7.pdf"

    def fake_convert(path):
        pdf.write_bytes(b"pdf-data")
        return True, str(pdf)

    monkeypatch.setattr(
        word_filler, "convert_to_pdf", fake_convert)

    docx_path, pdf_path = registry_history.ensure_history_files(7)

    assert docx_path == str(docx)
    assert pdf_path == str(pdf)
    assert pdf.exists()


def test_show_history_page_builds_labels_and_pagination(
    temp_db, monkeypatch
):
    batch_ids = []
    for index in range(9):
        batch_id, _ = _batch_with_order(
            temp_db, start=f"{219300 + index:07d}")
        temp_db.close_batch(batch_id)
        batch_ids.append(batch_id)

    calls = []
    monkeypatch.setattr(
        registry_history,
        "safe_edit_message_text",
        lambda **kwargs: calls.append(kwargs),
    )

    registry_history.show_history_page(500, 1, 0)

    first_page = calls[-1]
    buttons = [
        button
        for row in first_page["reply_markup"].keyboard
        for button in row
    ]
    view_buttons = [
        button for button in buttons
        if button.callback_data.startswith("registry_history_view_")
    ]
    assert len(view_buttons) == 8
    assert "ТТН 0219308" in view_buttons[0].text
    assert any(
        button.callback_data == "master_registry_history_page_1"
        for button in buttons)
    assert "страница 1 из 2" in first_page["text"]

    registry_history.show_history_page(500, 1, 1)

    second_page = calls[-1]
    second_buttons = [
        button
        for row in second_page["reply_markup"].keyboard
        for button in row
    ]
    second_view = [
        button for button in second_buttons
        if button.callback_data.startswith("registry_history_view_")
    ]
    assert len(second_view) == 1
    assert any(
        button.callback_data == "master_registry_history_page_0"
        for button in second_buttons)
    assert "страница 2 из 2" in second_page["text"]
    assert batch_ids[0] in [
        int(button.callback_data.rsplit("_", 1)[1])
        for button in second_view
    ]


def test_finish_batch_archives_registry_before_closing(
    temp_db, tmp_path, monkeypatch
):
    result = tmp_path / "Результат"
    result.mkdir()
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    batch_id, _ = _batch_with_order(temp_db)
    docx = result / f"Реестр_ТТН_batch{batch_id}.docx"
    pdf = result / f"Реестр_ТТН_batch{batch_id}.pdf"
    docx.write_bytes(b"docx-data")
    pdf.write_bytes(b"pdf-data")

    monkeypatch.setattr(
        registry_filler,
        "generate_registry",
        lambda *args, **kwargs: (str(docx), str(pdf)),
    )
    monkeypatch.setattr(registry.bot, "send_message", lambda *a, **k: None)
    monkeypatch.setattr(registry.bot, "send_document", lambda *a, **k: None)

    registry._finish_batch(500, batch_id)

    target = result / "История_реестров" / f"batch_{batch_id}"
    assert (target / docx.name).exists()
    assert (target / pdf.name).exists()
    assert temp_db.get_batch(batch_id)["closed_at"]


def test_finish_batch_closes_even_if_archive_fails(
    temp_db, tmp_path, monkeypatch
):
    result = tmp_path / "Результат"
    result.mkdir()
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(result))
    batch_id, _ = _batch_with_order(temp_db)
    docx = result / f"Реестр_ТТН_batch{batch_id}.docx"
    pdf = result / f"Реестр_ТТН_batch{batch_id}.pdf"
    docx.write_bytes(b"docx-data")
    pdf.write_bytes(b"pdf-data")

    monkeypatch.setattr(
        registry_filler,
        "generate_registry",
        lambda *args, **kwargs: (str(docx), str(pdf)),
    )
    monkeypatch.setattr(registry.bot, "send_message", lambda *a, **k: None)
    monkeypatch.setattr(registry.bot, "send_document", lambda *a, **k: None)

    def fail_archive(*args, **kwargs):
        raise OSError("нет места на диске")

    monkeypatch.setattr(
        registry_history, "archive_registry", fail_archive)

    registry._finish_batch(500, batch_id)

    assert temp_db.get_batch(batch_id)["closed_at"]

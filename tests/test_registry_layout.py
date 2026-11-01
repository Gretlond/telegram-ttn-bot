from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Mm
from pytest import approx, raises

import registry_filler


def test_registry_docx_is_a4_portrait(monkeypatch, tmp_path):
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(tmp_path))

    path = registry_filler.generate_registry_docx(
        [], "Иванов И.И.", "registry_a4_test"
    )
    doc = Document(path)

    assert len(doc.sections) == 1
    section = doc.sections[0]
    assert section.page_width == approx(Mm(210), abs=1000)
    assert section.page_height == approx(Mm(297), abs=1000)
    assert section.orientation == WD_ORIENT.PORTRAIT


def test_registry_rejects_two_orders_on_same_row(monkeypatch, tmp_path):
    monkeypatch.setattr(registry_filler, "RESULT_FOLDER", str(tmp_path))
    orders = [
        {'id': 1, 'order_row': 25, 'ttn_number': '0219200', 'date': ''},
        {'id': 2, 'order_row': 25, 'ttn_number': '0219199', 'date': ''},
    ]

    with raises(ValueError):
        registry_filler.generate_registry_docx(
            orders, "Мастер", "registry_duplicate_row")

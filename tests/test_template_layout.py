from pathlib import Path

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt


def _totals_table(doc):
    for table in doc.tables:
        if any(
            "total_vat_text" in cell.text
            for row in table.rows
            for cell in row.cells
        ):
            return table
    raise AssertionError("Таблица итогов не найдена")


def test_demo_template_keeps_totals_on_second_page():
    """Итоги и подписи не должны всплывать над датой на первой странице."""
    template = Path(__file__).resolve().parents[1] / "assets" / "Шаблон_ТТН_демо.docx"
    doc = Document(template)
    table = _totals_table(doc)

    # Раньше таблица была floating-таблицей с привязкой к верху страницы.
    assert table._tbl.tblPr.find(qn("w:tblpPr")) is None

    previous = table._tbl.getprevious()
    assert previous is not None
    assert previous.tag == qn("w:p")
    p_pr = previous.find(qn("w:pPr"))
    assert p_pr is not None
    # Итоги начинаются на второй странице через разрыв раздела, чтобы у
    # второй страницы был свой (меньший) верхний отступ.
    assert p_pr.find(qn("w:sectPr")) is not None
    assert len(doc.sections) == 2
    assert doc.sections[1].top_margin < doc.sections[0].top_margin


def test_demo_totals_rows_match_paper_form():
    template = Path(__file__).resolve().parents[1] / "assets" / "Шаблон_ТТН_демо.docx"
    doc = Document(template)
    table = _totals_table(doc)

    assert len(table.rows) == 5
    shipper_row = next(
        row
        for row in table.rows
        if any("shipper_handed_by" in cell.text for cell in row.cells)
    )
    assert any("consignee_received_by" in cell.text for cell in shipper_row.cells)


def test_demo_cargo_table_fits_content_width_and_centers_values():
    template = Path(__file__).resolve().parents[1] / "assets" / "Шаблон_ТТН_демо.docx"
    doc = Document(template)
    section = doc.sections[0]
    content_width = section.page_width - section.left_margin - section.right_margin

    table = next(
        table
        for table in doc.tables
        if any("{{cargo.cargo_name}}" in cell.text for row in table.rows for cell in row.cells)
    )
    cargo_row = next(
        row for row in table.rows
        if any("{{cargo.cargo_name}}" in cell.text for cell in row.cells)
    )

    assert abs(sum(column.width for column in table.columns) - content_width) < 10000
    assert table._tbl.tblPr.find(qn("w:tblInd")).get(qn("w:w")) == "0"
    assert table._tbl.tblPr.find(qn("w:tblLayout")).get(qn("w:type")) == "fixed"

    # Границы колонок сняты с типографского бланка: наименование шире,
    # «Ед. изм.» узкая, «Примечание» широкая. Иначе единица измерения
    # уезжает в «Количество» и весь ряд сдвигается на колонку вправо.
    expected_widths = [
        68.36, 11.48, 14.28, 23.98, 27.55, 10.20,
        22.70, 23.72, 18.88, 15.81, 27.04,
    ]
    actual_widths = [column.width.mm for column in table.columns]
    assert actual_widths == pytest.approx(expected_widths, abs=0.1)

    alignments = [cell.paragraphs[0].alignment for cell in cargo_row.cells]
    assert alignments[0] == WD_ALIGN_PARAGRAPH.LEFT
    assert all(alignment == WD_ALIGN_PARAGRAPH.CENTER for alignment in alignments[1:])


def test_demo_shipper_names_sit_above_preprinted_signature_lines():
    template = Path(__file__).resolve().parents[1] / "assets" / "Шаблон_ТТН_демо.docx"
    doc = Document(template)

    assert doc.sections[1].top_margin == pytest.approx(Mm(9.0), abs=1000)

    table = _totals_table(doc)
    signature_paragraphs = []
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                if (
                    "shipper_handed_by" in paragraph.text
                    or "consignee_received_by" in paragraph.text
                ):
                    signature_paragraphs.append(paragraph)

    assert len(signature_paragraphs) == 2
    by_key = {}
    for paragraph in signature_paragraphs:
        if "shipper_handed_by" in paragraph.text:
            by_key["shipper"] = paragraph
        if "consignee_received_by" in paragraph.text:
            by_key["consignee"] = paragraph

    # На бланке строки «Сдал» и «Принял» разнесены по высоте:
    # подпись сдающего чуть выше, принимающего — чуть ниже.
    assert by_key["shipper"].paragraph_format.space_before == pytest.approx(Pt(19), abs=1000)
    assert by_key["consignee"].paragraph_format.space_before == pytest.approx(Pt(37), abs=1000)


def test_demo_top_header_contains_only_unp_values():
    """Верхняя таблица и подпись УНП уже есть на типографском бланке."""
    template = Path(__file__).resolve().parents[1] / "assets" / "Шаблон_ТТН_демо.docx"
    doc = Document(template)

    table = doc.tables[0]
    assert len(table.rows) == 1
    assert len(table.columns) == 3
    assert [cell.text for cell in table.rows[0].cells] == [
        "{{shipper_unp}}",
        "{{consignee_unp}}",
        "{{customer_unp}}",
    ]
    text = " ".join(cell.text for cell in table.rows[0].cells)
    assert "УНП" not in text
    assert "Грузоотправитель" not in text
    assert "Грузополучатель" not in text
    assert "Заказчик" not in text


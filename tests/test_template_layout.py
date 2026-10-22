from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


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
    assert p_pr.find(qn("w:pageBreakBefore")) is not None

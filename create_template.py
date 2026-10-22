# =============================================================
# ГЕНЕРАТОР ИДЕАЛЬНОГО WORD-ШАБЛОНА ТТН (Для печати)
# =============================================================
import os
from docx import Document
from docx.shared import Pt, Cm, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL


def create_template():
    if not os.path.exists("Шаблоны"):
        os.makedirs("Шаблоны")

    doc = Document()

    # --- НАСТРОЙКА СТРАНИЦЫ (Альбомная А4, поля 1 см) ---
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Mm(297)
    section.page_height = Mm(210)
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.0)
    section.top_margin = Cm(1.0)
    section.bottom_margin = Cm(1.0)

    # Шрифт по умолчанию
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(9)

    # --- ЛИЦЕВАЯ СТОРОНА ---
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run("ТОВАРНО-ТРАНСПОРТНАЯ НАКЛАДНАЯ\n").bold = True
    p.add_run("Серия 3 № {{ waybill_number }} от {{ day }} {{ month }} {{ year }} г.").bold = True

    doc.add_paragraph()

    # Блок организаций
    table_orgs = doc.add_table(rows=3, cols=2)
    table_orgs.style = 'Table Grid'
    table_orgs.autofit = False
    for row in table_orgs.rows:
        row.cells[0].width = Cm(4.5)
        row.cells[1].width = Cm(23.0)

    orgs = [
        ("Отправитель", "{{ shipper }}"),
        ("Получатель", "{{ consignee }}"),
        ("Плательщик", "{{ customer }}")
    ]
    for i, (label, val) in enumerate(orgs):
        c1 = table_orgs.cell(i, 0)
        c1.text = label
        c1.paragraphs[0].runs[0].bold = True
        c2 = table_orgs.cell(i, 1)
        c2.text = val

    doc.add_paragraph()

    # Блок машины
    p = doc.add_paragraph()
    p.add_run("Автомобиль: ").bold = True
    p.add_run("{{ car_model }} ({{ car_plate }})   ")
    p.add_run("Прицеп: ").bold = True
    p.add_run("{{ trailer_info }}   ")
    p.add_run("Водитель: ").bold = True
    p.add_run("{{ driver_name }}")

    p = doc.add_paragraph()
    p.add_run("Пункт погрузки: ").bold = True
    p.add_run("{{ loading_point }}   ")
    p.add_run("Пункт разгрузки: ").bold = True
    p.add_run("{{ unloading_point }}")

    doc.add_paragraph()
    doc.add_paragraph("I. ТОВАРНЫЙ РАЗДЕЛ").bold = True

    # Главная таблица (12 колонок)
    table_goods = doc.add_table(rows=2, cols=12)
    table_goods.style = 'Table Grid'
    table_goods.autofit = False
    table_goods.allow_autofit = False

    headers = [
        "№\nп/п", "Наименование товара", "Ед.\nизм.", "Коли-\nчество",
        "Масса\nгруза, т", "Цена,\nруб. коп.", "Стоимость,\nруб. коп.", "Ставка\nНДС, %",
        "Сумма\nНДС, руб. коп.", "Стоимость\nс НДС, руб. коп.", "Кол-во\nмест", "Приме-\nчание"
    ]
    # Точные ширины в см (общая сумма 27.5 см влезает в А4)
    widths = [0.8, 7.7, 1.2, 1.8, 1.8, 2.0, 2.0, 1.5, 2.0, 2.2, 1.8, 2.2]

    for i, (h, w) in enumerate(zip(headers, widths)):
        cell = table_goods.cell(0, i)
        cell.text = h
        cell.width = Cm(w)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(8)

    # --- ВОЛШЕБНАЯ СТРОКА ДЛЯ БОТА ---
    row = table_goods.rows[1]
    row_cells = row.cells

    # Вставляем скрытые теги цикла (белый шрифт 1pt), чтобы они не портили вид
    def add_hidden_text(cell, text):
        p = cell.paragraphs[0]
        run = p.add_run(text)
        run.font.size = Pt(1)
        run.font.color.rgb = RGBColor(255, 255, 255)

    add_hidden_text(row_cells[0], "{%tr for cargo in cargos %}")
    p = row_cells[0].add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("{{ loop.index }}")

    tags = [
        "{{ cargo.cargo_name }}", "{{ cargo.unit }}", "{{ cargo.quantity }}",
        "{{ cargo.cargo_qty }}", "{{ cargo.price }}", "{{ cargo.total_cost }}",
        "{{ cargo.vat_rate }}", "{{ cargo.vat_cost }}", "{{ cargo.total_with_vat }}",
        "{{ cargo.places }}"
    ]

    for i, tag in enumerate(tags, start=1):
        row_cells[i].text = tag

    add_hidden_text(row_cells[11], "{%tr endfor %}")

    for i, cell in enumerate(row_cells):
        cell.width = Cm(widths[i])
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            for r in p.runs:
                if r.font.size != Pt(1):  # Не меняем скрытые теги
                    r.font.size = Pt(8)

    doc.add_paragraph()

    # Итоги
    p = doc.add_paragraph()
    p.add_run("Итого масса: ").bold = True
    p.add_run("{{ total_mass_text }}")

    p = doc.add_paragraph()
    p.add_run("Всего мест: ").bold = True
    p.add_run("{{ total_places_text }}")

    doc.add_paragraph()

    # Подписи
    table_signs = doc.add_table(rows=1, cols=3)
    table_signs.style = 'Table Grid'
    table_signs.autofit = False
    signs = [
        ("Отпуск разрешил:\n{{ release_allowed_by }}"),
        ("Главный бухгалтер:\n\n"),
        ("Отпустил:\n{{ shipper_handed_by }}")
    ]
    for i, text in enumerate(signs):
        cell = table_signs.cell(0, i)
        cell.width = Cm(9.1)
        cell.text = text
        for p in cell.paragraphs:
            p.paragraph_format.space_after = Pt(0)
            for r in p.runs:
                r.font.size = Pt(8)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run("Принял: ").bold = True
    p.add_run("{{ consignee_received_by }}")

    # --- ОБОРОТНАЯ СТОРОНА ---
    doc.add_page_break()

    p = doc.add_paragraph()
    p.add_run("II. ПОГРУЗО-РАЗГРУЗОЧНЫЕ ОПЕРАЦИИ").bold = True
    doc.add_paragraph("(Заполняется вручную)").italic = True

    doc.add_paragraph()

    p = doc.add_paragraph()
    p.add_run("III. ПРОЧИЕ СВЕДЕНИЯ").bold = True
    doc.add_paragraph("(Заполняется вручную)").italic = True

    doc.save("Шаблоны/Шаблон_ТТН.docx")
    print("✅ Идеальный шаблон Шаблоны/Шаблон_ТТН.docx успешно создан!")


if __name__ == "__main__":
    create_template()
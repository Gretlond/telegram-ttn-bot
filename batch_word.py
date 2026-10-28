# =============================================================
# СБОРКА ПАКЕТНЫХ WORD-ФАЙЛОВ ТТН
# =============================================================
"""Сборка двух файлов для ручной двусторонней печати.

Одна ТТН формируется существующим word_filler как документ из двух страниц:
первая страница — лицо, вторая — оборот. Для пакета каждая страница
повторяется заданное число раз (по умолчанию 4), при этом сохраняются
размер бумаги и поля исходного шаблона.
"""
import os
from copy import deepcopy

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


COPIES_PER_TTN = 4
SIDE_FRONT = "front"
SIDE_BACK = "back"


def _split_two_page_document(path):
    """Возвращает XML-блоки первой/второй страницы и их sectPr.

    В шаблоне ТТН первая страница заканчивается абзацем с w:sectPr,
    вторая — sectPr в конце body. Такой разрез не зависит от текста заявки
    и сохраняет индивидуальные поля каждой страницы.
    """
    doc = Document(path)
    body = doc.element.body
    children = list(body.iterchildren())

    if not children or children[-1].tag != qn("w:sectPr"):
        raise ValueError(f"В документе нет завершающего sectPr: {path}")

    final_sect_pr = children[-1]
    content = children[:-1]

    split_at = None
    for idx, child in enumerate(content):
        if child.tag != qn("w:p"):
            continue
        p_pr = child.find(qn("w:pPr"))
        if p_pr is not None and p_pr.find(qn("w:sectPr")) is not None:
            split_at = idx
            break

    if split_at is None:
        raise ValueError(f"Не найден разрыв между сторонами ТТН: {path}")

    page_one = content[:split_at + 1]
    page_two = content[split_at + 1:]
    if not page_one or not page_two:
        raise ValueError(f"ТТН должна состоять из двух страниц: {path}")

    first_sect_pr = page_one[-1].find(qn("w:pPr")).find(qn("w:sectPr"))
    if first_sect_pr is None:
        raise ValueError(f"Не найден sectPr первой страницы: {path}")

    return (
        page_one,
        page_two,
        deepcopy(first_sect_pr),
        deepcopy(final_sect_pr),
    )


def _remove_section_break(paragraph):
    """Убирает sectPr из последнего абзаца, оставляя его в body."""
    p_pr = paragraph.find(qn("w:pPr"))
    if p_pr is None:
        return
    sect_pr = p_pr.find(qn("w:sectPr"))
    if sect_pr is not None:
        p_pr.remove(sect_pr)
    if len(p_pr) == 0:
        paragraph.remove(p_pr)


def _section_break_paragraph(sect_pr):
    """Создаёт пустой абзац с разрывом раздела для второй стороны."""
    paragraph = OxmlElement("w:p")
    p_pr = OxmlElement("w:pPr")
    p_pr.append(deepcopy(sect_pr))
    paragraph.append(p_pr)
    return paragraph


def assemble_side_document(order_docx_paths, output_path, side, copies=COPIES_PER_TTN):
    """Собирает Word-файл только с одной стороной ТТН.

    Порядок заявок сохраняется: сначала все копии первой заявки, затем
    второй и так далее. Для каждой копии создаётся отдельный раздел,
    поэтому Word не склеивает страницы и не добавляет пустые листы.
    """
    if side not in (SIDE_FRONT, SIDE_BACK):
        raise ValueError(f"Неизвестная сторона ТТН: {side}")
    if not order_docx_paths:
        raise ValueError("Не передано ни одной заявки для пакета")
    if copies < 1:
        raise ValueError("Количество копий должно быть положительным")

    source_parts = [_split_two_page_document(path) for path in order_docx_paths]

    base = Document(order_docx_paths[0])
    body = base.element.body
    base_children = list(body.iterchildren())
    if not base_children or base_children[-1].tag != qn("w:sectPr"):
        raise ValueError("В базовом документе нет завершающего sectPr")

    base_final_sect_pr = base_children[-1]
    for child in base_children[:-1]:
        body.remove(child)

    for order_idx, (page_one, page_two, first_sect_pr, second_sect_pr) in enumerate(
        source_parts
    ):
        blocks = page_one if side == SIDE_FRONT else page_two
        for copy_idx in range(copies):
            is_last_page = (
                order_idx == len(source_parts) - 1 and copy_idx == copies - 1
            )
            inserted = []
            for block in blocks:
                clone = deepcopy(block)
                body.insert(len(body) - 1, clone)
                inserted.append(clone)

            if side == SIDE_FRONT and is_last_page and inserted:
                _remove_section_break(inserted[-1])
            elif side == SIDE_BACK and not is_last_page:
                body.insert(len(body) - 1, _section_break_paragraph(second_sect_pr))

    body.remove(base_final_sect_pr)
    final_sect_pr = source_parts[-1][2] if side == SIDE_FRONT else source_parts[-1][3]
    body.append(deepcopy(final_sect_pr))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    base.save(output_path)
    return output_path


def build_batch_documents(
    order_docx_paths, output_dir, output_prefix, copies=COPIES_PER_TTN
):
    """Создаёт пару файлов: передние и задние стороны всех заявок."""
    os.makedirs(output_dir, exist_ok=True)
    front_path = os.path.join(output_dir, f"{output_prefix}_перед.docx")
    back_path = os.path.join(output_dir, f"{output_prefix}_зад.docx")
    assemble_side_document(order_docx_paths, front_path, SIDE_FRONT, copies)
    assemble_side_document(order_docx_paths, back_path, SIDE_BACK, copies)
    return front_path, back_path

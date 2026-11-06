# =============================================================
# ИСТОРИЯ РЕЕСТРОВ ПАЧЕК
# =============================================================
"""Отдельное меню со всеми закрытыми реестрами мастера.

Файлы закрытых пачек копируются в «Результат/История_реестров», поэтому
реестр остаётся доступным и после печати. Если архивного файла нет,
реестр восстанавливается из базы.
"""
import os
import shutil
from datetime import datetime

from telebot import types

from config import bot
import batch_registry
import orders_db
import registry_filler
from utils import safe_edit_message_text

from log_setup import get_logger

logger = get_logger(__name__)

HISTORY_FOLDER = "История_реестров"
PAGE_SIZE = 8
DATE_FORMATS = ("%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d")


def parse_registry_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _row_sort_key(entry):
    row = entry["row"]
    if row is None:
        return (1, 0)
    try:
        return (0, -int(row))
    except (TypeError, ValueError):
        return (1, 0)


def build_registry_stats(orders, manual):
    """Собирает диапазон ТТН и дат для названия реестра.

    Первая накладная — верхняя строка реестра (25), последняя — нижняя.
    Даты берутся самые ранняя и самая поздняя среди записей.
    """
    entries = []
    for order in orders:
        entries.append({
            "row": order.get("order_row"),
            "ttn": str(order.get("ttn_number") or "").strip(),
            "date": order.get("date"),
        })
    for entry in manual:
        entries.append({
            "row": entry.get("target_row"),
            "ttn": str(entry.get("ttn_number") or "").strip(),
            "date": entry.get("date"),
        })

    with_ttn = [entry for entry in entries if entry["ttn"]]
    if with_ttn and all(entry["row"] is None for entry in with_ttn):
        # Без строк ориентируемся на номера: сверху реестра идёт
        # наибольший номер, снизу — наименьший.
        with_ttn.sort(
            key=lambda entry: (
                0, int(entry["ttn"])) if entry["ttn"].isdigit()
            else (1, entry["ttn"]),
            reverse=True)
    else:
        with_ttn.sort(key=_row_sort_key)

    parsed_dates = [
        parsed for parsed in (
            parse_registry_date(entry.get("date")) for entry in entries
        ) if parsed is not None
    ]

    return {
        "count": len(entries),
        "first_ttn": with_ttn[0]["ttn"] if with_ttn else "",
        "last_ttn": with_ttn[-1]["ttn"] if with_ttn else "",
        "first_date": min(parsed_dates) if parsed_dates else None,
        "last_date": max(parsed_dates) if parsed_dates else None,
    }


def format_ttn_range(stats):
    first = stats.get("first_ttn") or ""
    last = stats.get("last_ttn") or ""
    if not first:
        return ""
    if not last or first == last:
        return first
    return f"{first}–{last}"


def format_date_range(stats):
    first = stats.get("first_date")
    last = stats.get("last_date")
    if not first:
        return ""
    if not last or first == last:
        return first.strftime("%d.%m.%y")
    return f"{first.strftime('%d.%m.%y')}–{last.strftime('%d.%m.%y')}"


def format_registry_label(batch_id, stats):
    """Название реестра для меню истории."""
    parts = [f"№{batch_id}"]
    ttn_range = format_ttn_range(stats)
    if ttn_range:
        parts.append(f"ТТН {ttn_range}")
    date_range = format_date_range(stats)
    if date_range:
        parts.append(date_range)
    return " • ".join(parts)


def format_closed_at(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue
    return text


def _history_dir(batch_id):
    return os.path.join(
        registry_filler.RESULT_FOLDER, HISTORY_FOLDER,
        f"batch_{int(batch_id)}")


def _file_candidates(batch_id, suffix):
    batch_id = int(batch_id)
    folder = _history_dir(batch_id)
    names = (
        f"Реестр_ТТН_batch{batch_id}{suffix}",
        f"Реестр_ТТН_batch{batch_id}_частичный{suffix}",
    )
    candidates = [os.path.join(folder, name) for name in names]
    candidates.extend(
        os.path.join(registry_filler.RESULT_FOLDER, name) for name in names)
    return candidates


def _find_file(batch_id, suffix):
    for path in _file_candidates(batch_id, suffix):
        if os.path.isfile(path):
            return path
    return None


def archive_registry(batch_id, docx_path=None, pdf_path=None):
    """Копирует готовые файлы реестра в архив истории."""
    target = _history_dir(batch_id)
    os.makedirs(target, exist_ok=True)
    copied = []
    for path in (docx_path, pdf_path):
        if not path or not os.path.isfile(path):
            continue
        destination = os.path.join(target, os.path.basename(path))
        if os.path.abspath(destination) != os.path.abspath(path):
            shutil.copy2(path, destination)
        copied.append(destination)
    return copied


def ensure_history_files(batch_id):
    """Возвращает (docx, pdf) из архива или восстанавливает из базы."""
    batch_id = int(batch_id)
    docx_path = _find_file(batch_id, ".docx")
    pdf_path = _find_file(batch_id, ".pdf")

    if not docx_path:
        docx_path, pdf_path = batch_registry.regenerate_batch_registry(
            batch_id, output_name=f"Реестр_ТТН_batch{batch_id}")
        pdf_path = pdf_path or _find_file(batch_id, ".pdf")
    elif not pdf_path:
        try:
            from word_filler import convert_to_pdf
            ok, result = convert_to_pdf(docx_path)
            if ok:
                pdf_path = result
        except Exception as e:
            logger.exception(f"⚠️ Не удалось сделать PDF реестра: {e}")

    archive_registry(batch_id, docx_path, pdf_path)
    return docx_path, pdf_path


def _batch_stats(batch):
    orders = orders_db.get_batch_orders(batch["id"])
    manual = orders_db.get_manual_registry(batch["master_id"], batch["id"])
    return orders, manual, build_registry_stats(orders, manual)


def show_history_page(user_id, message_id, page=0):
    batches = orders_db.get_closed_batches(user_id)
    if not batches:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("⬅️ В кабинет", callback_data="master_back"))
        safe_edit_message_text(
            chat_id=user_id, message_id=message_id,
            text=("📚 *История реестров*\n\n"
                  "_Закрытых реестров пока нет._\n\n"
                  "Пачка попадёт сюда после заполнения и печати."),
            parse_mode='Markdown', reply_markup=m)
        return

    pages = max(1, (len(batches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    start = page * PAGE_SIZE
    chunk = batches[start:start + PAGE_SIZE]

    m = types.InlineKeyboardMarkup(row_width=1)
    for batch in chunk:
        _, _, stats = _batch_stats(batch)
        label = format_registry_label(batch["id"], stats)
        m.add(types.InlineKeyboardButton(
            f"📄 {label}",
            callback_data=f"registry_history_view_{batch['id']}"))

    if pages > 1:
        if page > 0:
            m.add(types.InlineKeyboardButton(
                "⬅️ Предыдущая страница",
                callback_data=f"master_registry_history_page_{page - 1}"))
        if page + 1 < pages:
            m.add(types.InlineKeyboardButton(
                "➡️ Следующая страница",
                callback_data=f"master_registry_history_page_{page + 1}"))
    m.add(types.InlineKeyboardButton("⬅️ В кабинет", callback_data="master_back"))

    text = (f"📚 *История реестров*\n\n"
            f"Закрытых реестров: *{len(batches)}*")
    if pages > 1:
        text += f" • страница {page + 1} из {pages}"
    text += ("\n\nВыберите реестр — пришлю Word и PDF. "
             "В названии указаны первая и последняя накладная и даты.")
    safe_edit_message_text(
        chat_id=user_id, message_id=message_id, text=text,
        parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_history')
def master_registry_history(call):
    show_history_page(call.message.chat.id, call.message.message_id, 0)


@bot.callback_query_handler(
    func=lambda c: c.data.startswith('master_registry_history_page_'))
def master_registry_history_page(call):
    try:
        page = int(call.data.rsplit('_', 1)[1])
    except (TypeError, ValueError):
        page = 0
    show_history_page(call.message.chat.id, call.message.message_id, page)


@bot.callback_query_handler(
    func=lambda c: c.data.startswith('registry_history_view_'))
def registry_history_view(call):
    user_id = call.message.chat.id
    try:
        batch_id = int(call.data.rsplit('_', 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "Реестр не найден.")
        return
    batch = orders_db.get_batch(batch_id)
    if not batch or int(batch["master_id"]) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.")
        return

    _, _, stats = _batch_stats(batch)
    label = format_registry_label(batch_id, stats)
    text = (f"📚 *Реестр пачки №{batch_id}*\n\n"
            f"📄 ТТН: `{format_ttn_range(stats) or '—'}`\n"
            f"📅 Даты: {format_date_range(stats) or '—'}\n"
            f"📦 Записей: {stats['count']}\n")
    if batch.get("closed_at"):
        text += f"🔒 Закрыта: {format_closed_at(batch['closed_at'])}\n"
    text += "\n_Файлы сохранены в истории и не пропадут после печати._"

    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton(
        "📥 Скачать Word + PDF",
        callback_data=f"registry_history_download_{batch_id}"))
    m.add(types.InlineKeyboardButton(
        "⬅️ К истории", callback_data="master_registry_history"))
    m.add(types.InlineKeyboardButton("⬅️ В кабинет", callback_data="master_back"))
    bot.answer_callback_query(call.id, label)
    safe_edit_message_text(
        chat_id=user_id, message_id=call.message.message_id, text=text,
        parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(
    func=lambda c: c.data.startswith('registry_history_download_'))
def registry_history_download(call):
    user_id = call.message.chat.id
    try:
        batch_id = int(call.data.rsplit('_', 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "Реестр не найден.")
        return
    batch = orders_db.get_batch(batch_id)
    if not batch or int(batch["master_id"]) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.")
        return

    bot.answer_callback_query(call.id, "⏳ Готовлю реестр...")
    try:
        docx_path, pdf_path = ensure_history_files(batch_id)
    except Exception as e:
        logger.exception(f"❌ Не удалось восстановить реестр №{batch_id}: {e}")
        bot.send_message(user_id, f"❌ Не удалось подготовить реестр: {e}")
        return

    _, _, stats = _batch_stats(batch)
    label = format_registry_label(batch_id, stats)
    try:
        if docx_path and os.path.exists(docx_path):
            with open(docx_path, 'rb') as f:
                bot.send_document(
                    user_id, f,
                    caption=f"📄 Реестр ТТН (Word) — {label}")
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                bot.send_document(
                    user_id, f,
                    caption=f"📄 Реестр ТТН (PDF) — {label}")
    except Exception as e:
        logger.exception(f"⚠️ Не удалось отправить реестр №{batch_id}: {e}")
        bot.send_message(user_id, f"⚠️ Не удалось отправить файл: {e}")

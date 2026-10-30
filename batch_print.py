# =============================================================
# ПАКЕТНАЯ ПЕЧАТЬ ТТН (Word, 4 экземпляра)
# =============================================================
import json
import os
import shutil
import tempfile
from datetime import datetime

from telebot import types

from config import bot, master_edit_state
from utils import safe_edit_message_text
import orders_db
import batch_word
import master_menu
import word_filler

PAGE_SIZE = 8
PENDING_FILE = os.path.join("data", "batch_print_pending.json")
SELECTION_FILE = os.path.join("data", "batch_selection.json")

_selection_state = {}
_selection_loaded = False


# =============================================================
# СОСТОЯНИЕ ВЫБОРА И ОЖИДАЮЩИЕ ПАКЕТЫ
# =============================================================
def _load_selection_all():
    global _selection_loaded
    if _selection_loaded:
        return
    _selection_loaded = True
    if not os.path.exists(SELECTION_FILE):
        return
    try:
        with open(SELECTION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ Не удалось прочитать выбор пакета: {e}")
        return
    if not isinstance(data, dict):
        return
    for raw_user_id, payload in data.items():
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            selected = payload.get("selected", [])
            page = payload.get("page", 0)
        elif isinstance(payload, list):
            selected = payload
            page = 0
        else:
            continue
        selected_ids = []
        for order_id in selected if isinstance(selected, list) else []:
            try:
                selected_ids.append(int(order_id))
            except (TypeError, ValueError):
                continue
        try:
            page = max(0, int(page))
        except (TypeError, ValueError):
            page = 0
        _selection_state[user_id] = {
            "selected": selected_ids,
            "page": page,
            "plan": None,
        }


def _save_selection_all():
    data = {}
    for user_id, session in _selection_state.items():
        selected = []
        for order_id in session.get("selected", []):
            try:
                selected.append(int(order_id))
            except (TypeError, ValueError):
                continue
        try:
            page = max(0, int(session.get("page", 0)))
        except (TypeError, ValueError):
            page = 0
        if selected or page:
            data[str(int(user_id))] = {
                "selected": selected,
                "page": page,
            }
    try:
        folder = os.path.dirname(os.path.abspath(SELECTION_FILE))
        os.makedirs(folder, exist_ok=True)
        tmp = SELECTION_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SELECTION_FILE)
    except Exception as e:
        print(f"⚠️ Не удалось сохранить выбор пакета: {e}")


def _reset_selection_cache():
    """Сбрасывает кэш (используется тестами и обслуживанием)."""
    global _selection_loaded
    _selection_state.clear()
    _selection_loaded = False


def _session(user_id):
    if not _selection_loaded:
        _load_selection_all()
    return _selection_state.setdefault(
        int(user_id), {"selected": [], "page": 0, "plan": None}
    )


def _load_pending_all():
    if not os.path.exists(PENDING_FILE):
        return {}
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"⚠️ Не удалось прочитать пакет печати: {e}")
        return {}


def _save_pending_all(data):
    folder = os.path.dirname(os.path.abspath(PENDING_FILE))
    os.makedirs(folder, exist_ok=True)
    tmp = PENDING_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PENDING_FILE)


def _get_pending(user_id):
    data = _load_pending_all().get(str(int(user_id)))
    return data if isinstance(data, dict) else None


def _put_pending(user_id, record):
    data = _load_pending_all()
    data[str(int(user_id))] = record
    _save_pending_all(data)


def _clear_pending(user_id, delete_files=False):
    data = _load_pending_all()
    record = data.pop(str(int(user_id)), None)
    _save_pending_all(data)
    if delete_files and record:
        for key in ("front_path", "back_path"):
            path = record.get(key)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"⚠️ Не удалось удалить {path}: {e}")


def _restore_selection_from_record(user_id, record):
    """Возвращает выбор из отменённого пакета, чтобы можно было исправить."""
    session = _session(user_id)
    selected = []
    for assignment in (record or {}).get("assignments", []) or []:
        try:
            selected.append(int(assignment["order_id"]))
        except (TypeError, ValueError, KeyError):
            continue
    session["selected"] = selected
    session["plan"] = None
    _save_selection_all()


# =============================================================
# ВЫБОР ЗАЯВОК
# =============================================================
def _available_orders(master_id):
    return [
        order for order in orders_db.get_master_orders(int(master_id))
        if order.get("status") in ("new", "confirmed")
        and not order.get("ttn_number")
        and not order.get("deleted_at")
    ]


def _select_all_order_ids(master_id):
    """Порядок для кнопки «Выделить все»: от старых заявок к новым.

    Первая заявка получает строку 25 и самый высокий номер ТТН.
    Ручной выбор эту сортировку не использует: там сохраняется порядок нажатий.
    """
    return [
        order["id"]
        for order in sorted(
            _available_orders(master_id),
            key=lambda order: int(order["id"]),
        )
    ]


def _active_batch_info(master_id):
    batch = orders_db.get_active_batch(int(master_id))
    if not batch:
        return None
    counter = int(batch.get("counter") or 0)
    return {
        "batch": batch,
        "counter": counter,
        "free": max(0, orders_db.BATCH_SIZE - counter),
        "next_ttn": orders_db.compute_ttn_number(batch["start_number"], -counter),
        "next_row": orders_db.BATCH_SIZE - counter,
    }


def _order_button_label(order, selected, selected_ids):
    mark = "✅" if order["id"] in selected_ids else "⬜"
    number = ""
    if order["id"] in selected_ids:
        number = f"{selected.index(order['id']) + 1}. "
    return f"{mark} {number}№{order['id']} • {order['date']} • {order['waybill_number']}"


def _selected_text(selected_ids):
    if not selected_ids:
        return "_Заявки пока не выбраны._"
    lines = []
    for index, order_id in enumerate(selected_ids, 1):
        order = orders_db.get_order(order_id)
        if not order:
            continue
        lines.append(
            f"{index}. №{order_id} • {order['date']} • {order['waybill_number']}"
        )
    return "\n".join(lines) if lines else "_Заявки пока не выбраны._"


def render_batch_menu(user_id, message_id=None, notice=None):
    pending = _get_pending(user_id)
    if pending:
        render_pending(user_id, message_id)
        return

    session = _session(user_id)
    available = _available_orders(user_id)
    available_ids = {order["id"] for order in available}
    cleaned_selection = [
        order_id for order_id in session.get("selected", [])
        if order_id in available_ids
    ]
    if cleaned_selection != session.get("selected", []):
        session["selected"] = cleaned_selection
        _save_selection_all()
    selected = session["selected"]
    active = _active_batch_info(user_id)
    free = active["free"] if active else orders_db.BATCH_SIZE

    total_pages = max(1, (len(available) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(int(session.get("page", 0)), 0), total_pages - 1)
    session["page"] = page
    page_orders = available[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    text = "🖨 *Пакетная печать ТТН*\n\n"
    if notice:
        text += f"{notice}\n\n"
    text += (
        f"Доступно нераспечатанных заявок: *{len(available)}*\n"
        f"Выбрано: *{len(selected)}* из {free} свободных мест\n\n"
        "Порядок печати — порядок нажатия. Первая выбранная заявка "
        "получит строку 25 реестра.\n"
        "«Выделить все» выбирает от старых к новым: строка 25 — "
        "самая старая заявка.\n\n"
    )
    if active:
        text += (
            f"📦 Партия №{active['batch']['id']}: сверху `{active['batch']['start_number']}`, "
            f"занято {active['counter']}/{orders_db.BATCH_SIZE}\n"
            f"Следующая: ТТН `{active['next_ttn']}`, строка {active['next_row']}\n\n"
        )
    else:
        text += (
            "📦 Активной партии нет. Номер верхней накладной запрошу "
            "перед формированием файлов.\n\n"
        )

    text += f"📋 *Выбранные заявки:*\n{_selected_text(selected)}"

    if not available:
        text += "\n\n✅ Нераспечатанных заявок нет."

    markup = types.InlineKeyboardMarkup(row_width=1)
    for order in page_orders:
        markup.add(types.InlineKeyboardButton(
            _order_button_label(order, selected, set(selected)),
            callback_data=f"batch_toggle_{order['id']}",
        ))

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"batch_page_{page - 1}"))
        nav.append(types.InlineKeyboardButton(
            f"Стр. {page + 1}/{total_pages}", callback_data="batch_page_noop"))
        if page < total_pages - 1:
            nav.append(types.InlineKeyboardButton("➡️", callback_data=f"batch_page_{page + 1}"))
        markup.row(*nav)

    if available:
        markup.add(types.InlineKeyboardButton(
            "✅ Выбрать все", callback_data="batch_select_all"))
    if selected:
        markup.add(types.InlineKeyboardButton(
            "🗑 Очистить выбор", callback_data="batch_clear"))
    if selected:
        markup.add(types.InlineKeyboardButton(
            f"📄 Сформировать Word ({len(selected)})", callback_data="batch_build"))
    markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="batch_print_menu"))
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))

    if message_id:
        safe_edit_message_text(
            chat_id=user_id, message_id=message_id, text=text,
            parse_mode="Markdown", reply_markup=markup,
        )
    else:
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "batch_print_menu")
def batch_print_menu(call):
    render_batch_menu(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "batch_page_noop")
def batch_page_noop(call):
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("batch_page_")
                            and c.data[len("batch_page_"):].isdigit())
def batch_page(call):
    user_id = call.message.chat.id
    try:
        page = int(call.data.replace("batch_page_", ""))
    except ValueError:
        bot.answer_callback_query(call.id, "Неверная страница.")
        return
    _session(user_id)["page"] = max(0, page)
    _save_selection_all()
    bot.answer_callback_query(call.id)
    render_batch_menu(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("batch_toggle_"))
def batch_toggle(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace("batch_toggle_", ""))
    order = orders_db.get_order(order_id)
    if not order or int(order["master_id"]) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.")
        return
    if order.get("deleted_at") or order.get("status") not in ("new", "confirmed") \
            or order.get("ttn_number"):
        bot.answer_callback_query(call.id, "Заявка уже недоступна для пакета.")
        render_batch_menu(user_id, call.message.message_id)
        return

    session = _session(user_id)
    selected = session.setdefault("selected", [])
    if order_id in selected:
        selected.remove(order_id)
        bot.answer_callback_query(call.id, "↩️ Убрана из пакета.")
    else:
        active = _active_batch_info(user_id)
        free = active["free"] if active else orders_db.BATCH_SIZE
        if len(selected) >= free:
            bot.answer_callback_query(
                call.id, f"В пачке осталось только {free} свободных мест.",
                show_alert=True)
            return
        selected.append(order_id)
        bot.answer_callback_query(call.id, "✅ Добавлена в пакет.")
    _save_selection_all()
    render_batch_menu(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "batch_select_all")
def batch_select_all(call):
    user_id = call.message.chat.id
    active = _active_batch_info(user_id)
    free = active["free"] if active else orders_db.BATCH_SIZE
    session = _session(user_id)
    selected = session.setdefault("selected", [])
    for order_id in _select_all_order_ids(user_id):
        if len(selected) >= free:
            break
        if order_id not in selected:
            selected.append(order_id)
    _save_selection_all()
    bot.answer_callback_query(call.id, f"Выбрано: {len(selected)}")
    render_batch_menu(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "batch_clear")
def batch_clear(call):
    user_id = call.message.chat.id
    session = _session(user_id)
    session["selected"] = []
    session["plan"] = None
    _save_selection_all()
    bot.answer_callback_query(call.id, "Выбор очищен.")
    render_batch_menu(user_id, call.message.message_id)


# =============================================================
# ПЛАН И ПОДТВЕРЖДЕНИЕ ДИАПАЗОНА
# =============================================================
def _make_assignments(order_ids, start_number, counter):
    if counter + len(order_ids) > orders_db.BATCH_SIZE:
        raise ValueError("В пачке недостаточно свободных строк")
    assignments = []
    for index, order_id in enumerate(order_ids):
        offset = counter + index
        order_row = orders_db.BATCH_SIZE - offset
        if order_row < 1:
            raise ValueError("Строка реестра вышла за границы")
        assignments.append({
            "order_id": int(order_id),
            "ttn_number": orders_db.compute_ttn_number(start_number, -offset),
            "order_row": order_row,
        })
    return assignments


def _format_plan_table(assignments):
    """Полная таблица предпросмотра: заявка, накладная, строка, ТТН."""
    lines = ["№   Заявка  Накладная   Стр.  ТТН"]
    for index, assignment in enumerate(assignments, 1):
        order = orders_db.get_order(assignment["order_id"]) or {}
        waybill = str(order.get("waybill_number") or "—")
        lines.append(
            f"{index:>2}.  {assignment['order_id']:>6}  {waybill:<10}  "
            f"{assignment['order_row']:>4}  {assignment['ttn_number']}"
        )
    return "```\n" + "\n".join(lines) + "\n```"


def show_batch_plan(user_id, selected_ids, start_number, batch_id, counter, message_id=None):
    try:
        assignments = _make_assignments(selected_ids, start_number, counter)
    except ValueError as e:
        bot.send_message(user_id, f"❌ {e}")
        return

    session = _session(user_id)
    session["plan"] = {
        "selected": list(selected_ids),
        "start_number": str(start_number),
        "batch_id": int(batch_id) if batch_id is not None else None,
        "counter": int(counter),
        "assignments": assignments,
    }

    first = assignments[0]
    last = assignments[-1]
    pages = len(assignments) * batch_word.COPIES_PER_TTN
    text = (
        "🧾 *Пакет к формированию*\n\n"
        f"Заявок: *{len(assignments)}*\n"
        f"ТТН: с `{first['ttn_number']}` (стр. {first['order_row']}) "
        f"по `{last['ttn_number']}` (стр. {last['order_row']})\n"
        f"В каждом файле: {pages} страниц "
        f"({len(assignments)} × {batch_word.COPIES_PER_TTN} экз.)\n\n"
        "📋 *Полный предпросмотр:*\n"
        f"{_format_plan_table(assignments)}\n\n"
        "Будут созданы два Word-файла: передние и задние стороны. "
        "Один номер ТТН — один комплект из 4 экземпляров.\n\n"
        "Партия останется открытой, если не заполнится до 25 заявок."
    )
    if batch_id is None:
        text += f"\n\n📦 Новая партия, номер сверху: `{start_number}`."
    else:
        text += f"\n\n📦 Текущая партия №{batch_id}."

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "✅ Сформировать Word-файлы", callback_data="batch_generate"))
    markup.add(types.InlineKeyboardButton(
        "⬅️ Изменить выбор", callback_data="batch_cancel_plan"))

    if message_id:
        safe_edit_message_text(
            chat_id=user_id, message_id=message_id, text=text,
            parse_mode="Markdown", reply_markup=markup,
        )
    else:
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "batch_build")
def batch_build(call):
    user_id = call.message.chat.id
    if _get_pending(user_id):
        bot.answer_callback_query(call.id, "Сначала подтвердите или отмените готовый пакет.")
        render_pending(user_id, call.message.message_id)
        return

    selected = list(_session(user_id).get("selected", []))
    if not selected:
        bot.answer_callback_query(call.id, "Выберите хотя бы одну заявку.", show_alert=True)
        return

    available_ids = {order["id"] for order in _available_orders(user_id)}
    if any(order_id not in available_ids for order_id in selected):
        bot.answer_callback_query(call.id, "Часть заявок уже изменилась. Обновите список.")
        render_batch_menu(user_id, call.message.message_id)
        return

    active = _active_batch_info(user_id)
    if active:
        if len(selected) > active["free"]:
            bot.answer_callback_query(
                call.id, f"Свободно только {active['free']} мест.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        show_batch_plan(
            user_id, selected, active["batch"]["start_number"],
            active["batch"]["id"], active["counter"], call.message.message_id)
        return

    master_edit_state[user_id] = {
        "action": "batch_waiting_start",
        "selected": selected,
    }
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        "📦 *Новая партия*\n\n"
        f"Выбрано заявок: *{len(selected)}*.\n"
        "Введите номер накладной, которая лежит *сверху пачки* "
        "(наибольший номер, с которого начинаете печать).\n\n"
        "Например: `0217975`\n\n"
        "_Отмена: /cancel_",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: master_edit_state.get(m.chat.id, {}).get("action")
                    == "batch_waiting_start")
def handle_batch_start(message):
    user_id = message.chat.id
    state = master_edit_state.get(user_id, {})
    text = (message.text or "").strip()
    if text.lower() in ("/cancel", "отмена"):
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Формирование пакета отменено.")
        render_batch_menu(user_id)
        return
    if not text:
        bot.send_message(user_id, "❌ Введите номер (или /cancel):")
        return

    selected = list(state.get("selected", []))
    master_edit_state.pop(user_id, None)
    if not selected:
        bot.send_message(user_id, "❌ Выбор заявок потерян. Начните заново.")
        render_batch_menu(user_id)
        return

    available_ids = {order["id"] for order in _available_orders(user_id)}
    if any(order_id not in available_ids for order_id in selected):
        bot.send_message(user_id, "⚠️ Часть заявок уже изменилась. Выберите заново.")
        render_batch_menu(user_id)
        return

    active = _active_batch_info(user_id)
    if active:
        show_batch_plan(
            user_id, selected, active["batch"]["start_number"],
            active["batch"]["id"], active["counter"])
    else:
        show_batch_plan(user_id, selected, text, None, 0)


@bot.callback_query_handler(func=lambda c: c.data == "batch_cancel_plan")
def batch_cancel_plan(call):
    user_id = call.message.chat.id
    _session(user_id)["plan"] = None
    bot.answer_callback_query(call.id, "Возврат к выбору.")
    render_batch_menu(user_id, call.message.message_id)


# =============================================================
# ГЕНЕРАЦИЯ WORD-ФАЙЛОВ
# =============================================================
def _send_batch_files(user_id, record):
    caption_front = (
        f"🖨 *Передние стороны* — {len(record['assignments'])} заявок, "
        f"по {batch_word.COPIES_PER_TTN} экземпляра.\n"
        "Печатайте этот файл первым."
    )
    caption_back = (
        f"🖨 *Задние стороны* — {len(record['assignments'])} заявок, "
        f"по {batch_word.COPIES_PER_TTN} экземпляра.\n"
        "Переверните пачку и печатайте этот файл вторым."
    )
    with open(record["front_path"], "rb") as f:
        bot.send_document(user_id, f, caption=caption_front, parse_mode="Markdown")
    with open(record["back_path"], "rb") as f:
        bot.send_document(user_id, f, caption=caption_back, parse_mode="Markdown")


def _batch_output_prefix(assignments):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    first = assignments[0]["ttn_number"]
    last = assignments[-1]["ttn_number"]
    return f"Пакет_ТТН_{stamp}_{first}_{last}"


def _generate_batch(user_id, plan):
    result_folder = os.path.abspath(word_filler.RESULT_FOLDER)
    os.makedirs(result_folder, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="batch_ttn_", dir=result_folder)
    order_paths = []
    front_path = back_path = None
    try:
        for assignment in plan["assignments"]:
            path = master_menu.rebuild_word_from_order(
                assignment["order_id"], output_dir=temp_dir)
            if not path or not os.path.exists(path):
                raise RuntimeError(
                    f"Не удалось создать Word для заявки №{assignment['order_id']}")
            order_paths.append(path)

        prefix = _batch_output_prefix(plan["assignments"])
        front_path, back_path = batch_word.build_batch_documents(
            order_paths, result_folder, prefix,
            copies=batch_word.COPIES_PER_TTN,
        )
    except Exception:
        for path in (front_path, back_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        raise
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    record = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assignments": plan["assignments"],
        "batch_id": plan["batch_id"],
        "counter": plan["counter"],
        "start_number": plan["start_number"],
        "front_path": front_path,
        "back_path": back_path,
    }
    _put_pending(user_id, record)
    return record


@bot.callback_query_handler(func=lambda c: c.data == "batch_generate")
def batch_generate(call):
    user_id = call.message.chat.id
    plan = _session(user_id).get("plan")
    if not plan:
        bot.answer_callback_query(call.id, "План устарел. Выберите заявки заново.")
        render_batch_menu(user_id, call.message.message_id)
        return
    if _get_pending(user_id):
        bot.answer_callback_query(call.id, "Готовый пакет уже есть.")
        render_pending(user_id, call.message.message_id)
        return

    bot.answer_callback_query(call.id, "⏳ Формирую Word-файлы...")
    status_msg = bot.send_message(user_id, "⏳ Формирую Word-файлы... Это может занять время.")
    try:
        record = _generate_batch(user_id, plan)
    except Exception as e:
        print(f"❌ Ошибка пакетной печати: {e}")
        _session(user_id)["plan"] = None
        try:
            bot.edit_message_text(
                chat_id=user_id, message_id=status_msg.message_id,
                text=f"❌ Не удалось сформировать пакет:\n{e}")
        except Exception:
            bot.send_message(user_id, f"❌ Не удалось сформировать пакет:\n{e}")
        return

    _session(user_id)["plan"] = None
    _session(user_id)["selected"] = []
    _save_selection_all()
    try:
        _send_batch_files(user_id, record)
        render_pending(user_id, status_msg.message_id)
    except Exception as e:
        print(f"⚠️ Пакет создан, но файлы не отправлены: {e}")
        try:
            bot.edit_message_text(
                chat_id=user_id, message_id=status_msg.message_id,
                text=(f"⚠️ Файлы созданы, но отправить их не удалось: {e}\n"
                      "Нажмите «Отправить файлы ещё раз»."))
        except Exception:
            bot.send_message(user_id, f"⚠️ Файлы созданы, но не отправлены: {e}")
        render_pending(user_id)


# =============================================================
# ГОТОВЫЙ ПАКЕТ: ПОДТВЕРЖДЕНИЕ / ОТПРАВКА / ОТМЕНА
# =============================================================
def render_pending(user_id, message_id=None):
    record = _get_pending(user_id)
    if not record:
        render_batch_menu(user_id, message_id)
        return

    if not all(
        record.get(key) and os.path.exists(record[key])
        for key in ("front_path", "back_path")
    ):
        _clear_pending(user_id)
        render_batch_menu(
            user_id, message_id,
            notice="⚠️ Файлы прошлого пакета не найдены. Выберите заявки заново.")
        return

    assignments = record.get("assignments", [])
    first = assignments[0]
    last = assignments[-1]
    text = (
        "📦 *Пакет сформирован*\n\n"
        f"Заявок: *{len(assignments)}*\n"
        f"ТТН: с `{first['ttn_number']}` (стр. {first['order_row']}) "
        f"по `{last['ttn_number']}` (стр. {last['order_row']})\n"
        f"Файлы: {len(assignments) * batch_word.COPIES_PER_TTN} страниц каждый\n\n"
        "📋 *Состав пакета:*\n"
        f"{_format_plan_table(assignments)}\n\n"
        "🖨 *Порядок печати:*\n"
        "1. Распечатайте файл передних сторон.\n"
        "2. Переверните всю пачку.\n"
        "3. Распечатайте файл задних сторон.\n"
        "4. Убедитесь, что стороны совпали, и нажмите «Подтвердить печать».\n\n"
        "⚠️ Заявки попадут в реестр только после подтверждения. "
        "Если вы уже напечатали пачку, не отменяйте пакет."
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "✅ Подтвердить печать", callback_data="batch_confirm_print"))
    markup.add(types.InlineKeyboardButton(
        "📤 Отправить файлы ещё раз", callback_data="batch_resend"))
    markup.add(types.InlineKeyboardButton(
        "❌ Отменить пакет", callback_data="batch_cancel_pending"))

    if message_id:
        safe_edit_message_text(
            chat_id=user_id, message_id=message_id, text=text,
            parse_mode="Markdown", reply_markup=markup,
        )
    else:
        bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "batch_resend")
def batch_resend(call):
    user_id = call.message.chat.id
    record = _get_pending(user_id)
    if not record:
        bot.answer_callback_query(call.id, "Пакет не найден.")
        render_batch_menu(user_id, call.message.message_id)
        return
    bot.answer_callback_query(call.id, "Отправляю файлы...")
    try:
        _send_batch_files(user_id, record)
        render_pending(user_id, call.message.message_id)
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Не удалось отправить файлы: {e}")


@bot.callback_query_handler(func=lambda c: c.data == "batch_cancel_pending")
def batch_cancel_pending(call):
    user_id = call.message.chat.id
    record = _get_pending(user_id)
    if not record:
        bot.answer_callback_query(call.id, "Пакет уже отменён.")
        render_batch_menu(user_id, call.message.message_id)
        return
    _restore_selection_from_record(user_id, record)
    _clear_pending(user_id, delete_files=True)
    bot.answer_callback_query(call.id, "Пакет отменён.")
    bot.send_message(
        user_id,
        "❌ Пакет отменён. Номера ТТН и реестр не изменялись.\n"
        "Выбор заявок восстановлен — можно исправить и сформировать пакет "
        "заново.\n"
        "Если файлы уже были напечатаны, они не попадут в реестр.")
    render_batch_menu(user_id)


def _validate_pending_orders(user_id, record):
    for assignment in record.get("assignments", []):
        order = orders_db.get_order(assignment["order_id"])
        if not order or int(order["master_id"]) != int(user_id):
            return False, f"Заявка №{assignment['order_id']} не найдена."
        if order.get("deleted_at"):
            return False, f"Заявка №{assignment['order_id']} удалена."
        if order.get("ttn_number") or order.get("status") not in ("new", "confirmed"):
            return False, f"Заявка №{assignment['order_id']} уже изменилась."
    return True, ""


def _invalidate_stale_pending(user_id, reason):
    record = _get_pending(user_id)
    _restore_selection_from_record(user_id, record)
    _clear_pending(user_id, delete_files=True)
    bot.send_message(
        user_id,
        f"⚠️ {reason}\nПакет отменён, изменения в реестр не внесены. "
        "Сформируйте пакет заново.")


@bot.callback_query_handler(func=lambda c: c.data == "batch_confirm_print")
def batch_confirm_print(call):
    user_id = call.message.chat.id
    record = _get_pending(user_id)
    if not record:
        bot.answer_callback_query(call.id, "Пакет не найден.")
        render_batch_menu(user_id, call.message.message_id)
        return

    ok, reason = _validate_pending_orders(user_id, record)
    if not ok:
        bot.answer_callback_query(call.id, "Пакет устарел.", show_alert=True)
        _invalidate_stale_pending(user_id, reason)
        return

    active = orders_db.get_active_batch(user_id)
    created_batch = False
    if record.get("batch_id") is None:
        if active:
            bot.answer_callback_query(call.id, "Появилась другая активная пачка.", show_alert=True)
            _invalidate_stale_pending(
                user_id, "Пока пакет был готов, открылась другая пачка.")
            return
        batch_id = orders_db.create_batch(user_id, record["start_number"])
        created_batch = True
        expected_counter = 0
    else:
        if not active or int(active["id"]) != int(record["batch_id"]):
            bot.answer_callback_query(call.id, "Активная пачка изменилась.", show_alert=True)
            _invalidate_stale_pending(
                user_id, "Активная пачка была закрыта или изменена.")
            return
        if int(active["counter"]) != int(record["counter"]):
            bot.answer_callback_query(call.id, "Счётчик пачки изменился.", show_alert=True)
            _invalidate_stale_pending(
                user_id, "После формирования пакета в пачке появились другие заявки.")
            return
        if str(active["start_number"]) != str(record["start_number"]):
            bot.answer_callback_query(call.id, "Номер сверху пачки изменён.", show_alert=True)
            _invalidate_stale_pending(
                user_id, "Номер сверху пачки был изменён.")
            return
        batch_id = int(active["id"])
        expected_counter = int(record["counter"])

    bot.answer_callback_query(call.id, "⏳ Подтверждаю...")
    try:
        assignments = orders_db.assign_orders_to_batch(
            batch_id,
            [a["order_id"] for a in record["assignments"]],
            expected_counter=expected_counter,
        )
    except Exception as e:
        print(f"❌ Ошибка подтверждения пакета: {e}")
        if created_batch:
            try:
                orders_db.close_batch(batch_id)
            except Exception:
                pass
        bot.send_message(
            user_id,
            f"❌ Не удалось подтвердить пакет: {e}\n"
            "Изменения не внесены. Проверьте пачку и попробуйте снова.")
        return

    # Фиксируем аудит и уведомляем водителей только после успешной транзакции.
    for assignment in assignments:
        orders_db.log_order_event(
            assignment["order_id"], user_id, "printed",
            {
                "ttn_number": assignment["ttn_number"],
                "order_row": assignment["order_row"],
                "batch_id": batch_id,
                "source": "batch",
            },
        )
        order = orders_db.get_order(assignment["order_id"])
        driver_id = order.get("driver_id") if order else None
        if driver_id:
            try:
                bot.send_message(
                    int(driver_id),
                    f"✅ Ваша заявка №{assignment['order_id']} "
                    f"(от {order['date']}, путевой {order['waybill_number']}) "
                    f"распечатана мастером.",
                )
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление водителю: {e}")

    orders_db.log_order_event(None, user_id, "batch_printed", {
        "batch_id": batch_id,
        "count": len(assignments),
        "orders": assignments,
    })
    _clear_pending(user_id, delete_files=False)
    _selection_state.pop(user_id, None)
    _save_selection_all()

    first = assignments[0]
    last = assignments[-1]
    text = (
        "✅ *Печать подтверждена*\n\n"
        f"Внесено в реестр заявок: *{len(assignments)}*\n"
        f"ТТН: с `{first['ttn_number']}` (стр. {first['order_row']}) "
        f"по `{last['ttn_number']}` (стр. {last['order_row']})\n"
    )
    batch = orders_db.get_batch(batch_id)
    if batch:
        text += f"📦 В пачке: {int(batch['counter'])}/{orders_db.BATCH_SIZE}\n"
    text += "\nФайлы Word остались в чате — по ним можно перепечатать пакет."

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "📦 Текущий реестр", callback_data="master_registry"))
    markup.add(types.InlineKeyboardButton(
        "⬅️ В меню", callback_data="master_back"))
    bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=markup)

    if batch and int(batch["counter"]) >= orders_db.BATCH_SIZE:
        from registry import _finish_batch
        _finish_batch(user_id, batch_id)

# =============================================================
# ВОДИТЕЛЬ: ПРОВЕРКА ЗАЯВКИ, ОТПРАВКА И РЕДАКТИРОВАНИЕ
# =============================================================
import copy
from telebot import types

from config import (bot, user_data, last_orders, save_last_orders,
                    YOUR_TELEGRAM_ID)
from utils import (safe_edit_message_text, strip_driver_prefix,
                   calculate_total_mass_text, find_masters_by_loading,
                   calculate_total_places_text_master,
                   calculate_vat_totals, amount_to_words_parts)
from keyboards import (get_date_keyboard, get_trailer_keyboard,
                       get_loading_keyboard, get_unloading_keyboard)
from database import CARS, UNITS
from word_filler import fill_documents
import orders_db
from driver_order_ui import show_summary, show_edit_cargos_list



_confirm_in_progress = set()


def _notify_admin_safe(text):
    try:
        bot.send_message(YOUR_TELEGRAM_ID, text)
    except Exception as e:
        print(f"⚠️ Не удалось уведомить администратора: {e}")


@bot.callback_query_handler(func=lambda c: c.data == 'confirm_order')
def confirm_order(call):
    user_id = call.message.chat.id
    data = user_data.get(user_id, {})
    if data.get('submitted'):
        bot.answer_callback_query(call.id, "✅ Эта заявка уже отправлена.")
        return
    # Защита от двойного нажатия: второй обработчик не должен успеть
    # сохранить ту же заявку ещё раз.
    if user_id in _confirm_in_progress:
        bot.answer_callback_query(call.id, "⏳ Заявка уже отправляется, подождите...")
        return
    cargos = data.get('cargos', [])
    if not cargos:
        bot.answer_callback_query(call.id, "Добавьте хотя бы один груз!")
        return

    _confirm_in_progress.add(user_id)
    try:
        driver_clean = strip_driver_prefix(data.get('driver_name', ''))
        data['driver_name'] = driver_clean
        data['cargo_accepted_by'] = f"Водитель {driver_clean}" if driver_clean else ''
        total_mass_str, total_mass_text = calculate_total_mass_text(cargos)
        data['total_qty'] = total_mass_str
        data['total_mass_text'] = total_mass_text
        data['total_places_text'] = calculate_total_places_text_master(cargos) or 'Навал'

        _, total_vat, total_with_vat = calculate_vat_totals(cargos)
        data['total_vat_text'], data['total_vat_cents'] = amount_to_words_parts(total_vat)
        data['total_with_vat_text'], data['total_with_vat_cents'] = amount_to_words_parts(total_with_vat)

        summary = (f"✅ *Новая заявка*\n\n"
                   f"📄 {data.get('waybill_number', '-')}\n"
                   f"📅 {data.get('day', '-')}.{data.get('month', '-')}.{data.get('year', '-')}\n"
                   f"👤 {data.get('driver_name', '-')}\n"
                   f"🚛 {data.get('car_model', '-')} ({data.get('car_plate', '-')})\n"
                   f"🚚 {data.get('trailer_info', '-')}\n"
                   f"📍 {data.get('loading_point', '-')}\n"
                   f"🏁 {data.get('unloading_point', '-')}\n")
        for i, c in enumerate(cargos, 1):
            summary += (f"\n*{i}.* {c['cargo_name']}\n"
                        f"  Рейсов: {c.get('trips', '-')}, Ед.: {c.get('unit', '-')}, "
                        f"Кол-во: {c.get('quantity', c.get('cargo_qty'))}\n")

        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="⏳ Формирую документ...")

        # Сначала документ. Если Word/шаблон упал, заявка не считается
        # отправленной и водитель может повторить попытку.
        try:
            driver_full = data.get('driver_name', 'Неизвестный')
            driver_clean_for_file = driver_full.replace(' ', '')
            date_str = f"{data.get('day', '00')}.{data.get('month', '00')}.{data.get('year', '00')}"
            waybill = data.get('waybill_number', 'без_номера')
            output_name = f"ТТН{driver_clean_for_file}{date_str}{waybill}"
            data_to_fill = data.copy()
            data_to_fill['cargos'] = cargos
            _, _, merged_path = fill_documents(data_to_fill, output_name)
        except Exception as e:
            print(f"Ошибка Word: {e}")
            _notify_admin_safe(f"❌ Ошибка Word при заявке водителя {user_id}: {e}")
            bot.send_message(user_id, "❌ Не удалось сформировать документ. "
                                      "Заявка НЕ отправлена. Попробуйте ещё раз.")
            return

        master_ids = find_masters_by_loading(data.get('loading_point', ''))
        if not master_ids:
            # Не теряем заявку: отправляем администратору, чтобы он назначил мастера.
            master_ids = [YOUR_TELEGRAM_ID]
            _notify_admin_safe(
                f"⚠️ Для заявки водителя {user_id} не найден мастер по погрузке "
                f"«{data.get('loading_point', '')}». Заявка сохранена для администратора.")

        created = []
        save_errors = []
        for m_id in master_ids:
            try:
                oid = orders_db.save_order(data, master_id=m_id, driver_id=user_id)
                created.append((m_id, oid))
            except Exception as e:
                print(f"Ошибка БД для мастера {m_id}: {e}")
                save_errors.append(f"мастер {m_id}: {e}")

        if not created:
            _notify_admin_safe(
                f"❌ Не удалось сохранить заявку водителя {user_id}: "
                + "; ".join(save_errors))
            bot.send_message(user_id, "❌ Не удалось сохранить заявку. "
                                      "Администратор уведомлён, попробуйте позже.")
            return

        # Заявка уже сохранена в БД. Фиксируем успех до отправки,
        # чтобы повторное нажатие не создало дубль даже при сбое сети.
        order_ids = [oid for _, oid in created]
        data['submitted'] = True
        data['last_order_ids'] = order_ids
        template = copy.deepcopy(data)
        template.pop('submitted', None)
        template.pop('last_order_ids', None)
        last_orders[user_id] = template
        last_orders[user_id]['last_order_id'] = order_ids[0]
        last_orders[user_id]['last_order_ids'] = order_ids
        save_last_orders()

        sent_count = 0
        send_errors = []
        for m_id, oid in created:
            master_text = summary + f"\n🆔 *Заявка №{oid}*"
            try:
                msg = bot.send_message(m_id, master_text, parse_mode='Markdown')
                orders_db.update_order_field(oid, 'master_message_id', msg.message_id)
                bot.send_message(m_id, "📄 Документ:")
                with open(merged_path, 'rb') as f:
                    bot.send_document(m_id, f, caption=f"📄 Заявка №{oid}")
                sent_count += 1
            except Exception as e:
                print(f"Ошибка отправки мастеру {m_id}: {e}")
                send_errors.append(f"мастер {m_id}, заявка №{oid}: {e}")

        if save_errors or send_errors or sent_count < len(created):
            _notify_admin_safe(
                "⚠️ Заявка сохранена, но были ошибки доставки/сохранения:\n"
                + "\n".join(save_errors + send_errors)
                + f"\nЗаявки: {', '.join(map(str, order_ids))}")

        if sent_count:
            bot.send_message(
                user_id,
                f"✅ Заявка отправлена мастеру. Номер: {', '.join(map(str, order_ids))}")
        else:
            bot.send_message(
                user_id,
                f"⚠️ Заявка сохранена (№{', '.join(map(str, order_ids))}), "
                "но отправить мастеру не удалось. Администратор уведомлён.")

        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🗑 Отозвать", callback_data="recall_order"),
              types.InlineKeyboardButton("🔄 Ещё заявка", callback_data="role_driver"))
        bot.send_message(user_id, "Что дальше?", reply_markup=m)
    finally:
        _confirm_in_progress.discard(user_id)


# =============================================================
# РЕДАКТИРОВАНИЕ ВОДИТЕЛЕМ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'edit_order')
def edit_order(call):
    user_id = call.message.chat.id
    user_data[user_id]['editing'] = True
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("📄 Путевой", callback_data="edit_waybill"),
          types.InlineKeyboardButton("📅 Дата", callback_data="edit_date"))
    m.add(types.InlineKeyboardButton("🚚 Прицеп", callback_data="edit_trailer"),
          types.InlineKeyboardButton("📍 Погрузка", callback_data="edit_loading"))
    m.add(types.InlineKeyboardButton("🏁 Разгрузка", callback_data="edit_unloading"),
          types.InlineKeyboardButton("📦 Грузы", callback_data="edit_cargos"))
    m.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_summary"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="✏️ Что изменить?",
                           parse_mode='Markdown', reply_markup=m)





@bot.callback_query_handler(func=lambda c: c.data == 'edit_cargos')
def edit_cargos(call):
    show_edit_cargos_list(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: (
    c.data.startswith('edit_cargo_')
    and not c.data.startswith('edit_cargo_trips_')
    and not c.data.startswith('edit_cargo_mass_')
    and not c.data.startswith('edit_cargo_unit_')
    and not c.data.startswith('edit_cargo_del_')
))
def show_cargo_edit_card(call):
    user_id = call.message.chat.id
    idx = int(call.data.replace('edit_cargo_', ''))
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Груз не найден."); return
    c = cargos[idx]
    text = (f"📦 *Груз {idx + 1}*\n\n"
            f"Название: {c['cargo_name']}\n"
            f"🔢 Рейсов: {c.get('trips', '—')}\n"
            f"⚖️ Масса: {c.get('cargo_qty', '—')}\n"
            f"📏 Единица: {c.get('unit', '—')}\n\nЧто изменить?")
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🔢 Рейсы", callback_data=f"edit_cargo_trips_{idx}"),
          types.InlineKeyboardButton("⚖️ Масса", callback_data=f"edit_cargo_mass_{idx}"))
    m.add(types.InlineKeyboardButton("📏 Единица", callback_data=f"edit_cargo_unit_{idx}"),
          types.InlineKeyboardButton("🗑 Удалить", callback_data=f"edit_cargo_del_{idx}"))
    m.add(types.InlineKeyboardButton("⬅️ К списку грузов", callback_data="edit_cargos"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('edit_cargo_trips_'))
def start_edit_cargo_trips(call):
    user_id = call.message.chat.id
    idx = int(call.data.replace('edit_cargo_trips_', ''))
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['editing_cargo_idx'] = idx
    c = cargos[idx]
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=(f"📦 *{c['cargo_name']}*\n\n"
                                 f"Введите *новое количество рейсов*:\n\n_Отмена: /cancel_"),
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, save_edit_cargo_trips)


def save_edit_cargo_trips(message):
    user_id = message.chat.id
    if (message.text or '').strip().lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('editing_cargo_idx', None)
        bot.send_message(user_id, "❌ Отменено.")
        show_summary(user_id); return
    text = (message.text or '').strip().replace(',', '.')
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число (или /cancel):")
        bot.register_next_step_handler(message, save_edit_cargo_trips); return
    idx = user_data[user_id].get('editing_cargo_idx')
    if idx is None:
        bot.send_message(user_id, "Сессия истекла."); return
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.send_message(user_id, "Груз не найден."); return
    car_id = user_data[user_id].get('car_id')
    capacity = CARS.get(car_id, {}).get('capacity', 0)
    if capacity == 0:
        bot.send_message(user_id, "❌ Ошибка грузоподъёмности."); return
    total_weight = round(float(capacity) * float(text), 2)
    total_weight_str = (str(int(total_weight)) if total_weight == int(total_weight)
                        else f"{total_weight:.2f}".rstrip('0').rstrip('.').replace('.', ','))
    cargos[idx]['trips'] = text.replace('.', ',')
    cargos[idx]['cargo_qty'] = total_weight_str
    cargos[idx]['quantity'] = total_weight_str
    user_data[user_id].pop('editing_cargo_idx', None)
    bot.send_message(user_id, f"✅ Рейсов: {text}\n⚖️ Масса: {total_weight_str} т")
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('edit_cargo_mass_'))
def start_edit_cargo_mass(call):
    user_id = call.message.chat.id
    idx = int(call.data.replace('edit_cargo_mass_', ''))
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['editing_cargo_idx'] = idx
    c = cargos[idx]
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=(f"📦 *{c['cargo_name']}*\n\n"
                                 f"Текущая масса: {c.get('cargo_qty', '—')}\n\n"
                                 f"Введите *новое значение массы*:\n\n_Отмена: /cancel_"),
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, save_edit_cargo_mass)


def save_edit_cargo_mass(message):
    user_id = message.chat.id
    if (message.text or '').strip().lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('editing_cargo_idx', None)
        bot.send_message(user_id, "❌ Отменено.")
        show_summary(user_id); return
    text = (message.text or '').strip().replace(',', '.')
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число (или /cancel):")
        bot.register_next_step_handler(message, save_edit_cargo_mass); return
    idx = user_data[user_id].get('editing_cargo_idx')
    if idx is None:
        bot.send_message(user_id, "Сессия истекла."); return
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.send_message(user_id, "Груз не найден."); return
    value = text.replace('.', ',')
    cargos[idx]['cargo_qty'] = value
    cargos[idx]['quantity'] = value
    user_data[user_id].pop('editing_cargo_idx', None)
    bot.send_message(user_id, f"✅ Масса обновлена: {value}")
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('edit_cargo_unit_'))
def start_edit_cargo_unit(call):
    user_id = call.message.chat.id
    idx = int(call.data.replace('edit_cargo_unit_', ''))
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['editing_cargo_idx'] = idx
    c = cargos[idx]
    m = types.InlineKeyboardMarkup(row_width=2)
    for unit_id, unit_name in UNITS.items():
        m.add(types.InlineKeyboardButton(unit_name,
                                         callback_data=f"set_cargo_unit_{unit_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"edit_cargo_{idx}"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=(f"📦 *{c['cargo_name']}*\n\n"
                                 f"Текущая единица: {c.get('unit', '—')}\n\n"
                                 f"Выберите новую единицу:"),
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('set_cargo_unit_'))
def set_cargo_unit(call):
    user_id = call.message.chat.id
    unit_id = call.data.replace('set_cargo_unit_', '')
    if unit_id not in UNITS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    idx = user_data[user_id].get('editing_cargo_idx')
    if idx is None:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Ошибка"); return
    cargos[idx]['unit'] = UNITS[unit_id]
    user_data[user_id].pop('editing_cargo_idx', None)
    bot.answer_callback_query(call.id, f"✅ Единица: {UNITS[unit_id]}")
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('edit_cargo_del_'))
def del_cargo_existing(call):
    user_id = call.message.chat.id
    idx = int(call.data.replace('edit_cargo_del_', ''))
    cargos = user_data[user_id].get('cargos', [])
    if idx < 0 or idx >= len(cargos):
        bot.answer_callback_query(call.id, "Ошибка"); return
    if len(cargos) <= 1:
        bot.answer_callback_query(call.id,
                                  "⚠️ В заявке должен быть хотя бы один груз.",
                                  show_alert=True)
        return
    removed = cargos.pop(idx)
    bot.answer_callback_query(call.id, f"🗑 Удалён: {removed['cargo_name'][:30]}")
    show_edit_cargos_list(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'back_to_summary')
def back_to_summary(call):
    user_id = call.message.chat.id
    user_data[user_id].pop('editing', None)
    user_data[user_id].pop('editing_cargo_idx', None)
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'edit_waybill')
def edit_waybill(call):
    user_id = call.message.chat.id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="📄 Новый номер путевого:")
    bot.register_next_step_handler_by_chat_id(user_id, save_waybill)


def save_waybill(message):
    user_id = message.chat.id
    text = (message.text or '').strip()
    if not text:
        bot.send_message(user_id, "❌ Введите номер путевого листа:")
        bot.register_next_step_handler_by_chat_id(user_id, save_waybill)
        return
    user_data[user_id]['waybill_number'] = text
    user_data[user_id].pop('editing', None)
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'edit_date')
def edit_date(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="📅 Новая дата:", reply_markup=get_date_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'edit_trailer')
def edit_trailer(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🚚 Прицеп:", reply_markup=get_trailer_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'edit_loading')
def edit_loading(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="📍 Погрузка:", reply_markup=get_loading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'edit_unloading')
def edit_unloading(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🏁 Разгрузка:", reply_markup=get_unloading_keyboard())


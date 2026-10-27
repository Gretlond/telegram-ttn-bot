# =============================================================
# РЕДАКТИРОВАНИЕ ЗАЯВКИ МАСТЕРОМ
# =============================================================
from telebot import types
from datetime import datetime, timedelta

from config import bot, user_data, master_edit_state, YOUR_TELEGRAM_ID
from utils import safe_edit_message_text, parse_order_index
from keyboards import get_main_keyboard
from master_menu import show_master_menu, rebuild_word_from_order
import orders_db


# =============================================================
# /CANCEL
# =============================================================
@bot.message_handler(commands=['cancel'])
def cancel_any_input(message):
    user_id = message.chat.id
    if user_data.get(user_id, {}).get('reg_driver'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard())
        return

    if master_edit_state.get(user_id, {}).get('action') == 'manual_reg':
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        from registry import render_current_registry
        render_current_registry(user_id)
        return

    state = master_edit_state.pop(user_id, None)
    if state:
        order_id = state.get('order_id')
        bot.send_message(user_id, "❌ Действие отменено.")
        if order_id:
            show_master_edit_menu(user_id, order_id)
        else:
            show_master_menu(user_id)
    else:
        bot.send_message(user_id, "Нечего отменять.", reply_markup=get_main_keyboard())

# =============================================================
# МЕНЮ РЕДАКТИРОВАНИЯ
# =============================================================
def show_master_edit_menu(user_id, order_id, message_id=None):
    order = orders_db.get_order(order_id)
    if not order: return
    text = (f"✏️ *Редактирование заявки №{order_id}*\n\n"
            f"📄 Путевой: {order['waybill_number']}\n📅 Дата: {order['date']}\n"
            f"🚛 {order['car_model']} ({order['car_plate']})\n🚚 Прицеп: {order['trailer_info']}\n"
            f"📍 {order['loading_point']} → {order['unloading_point']}\n\nВыберите действие:")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📝 Изменить существующие данные",
                                     callback_data=f"medit_existing_{order_id}"))
    m.add(types.InlineKeyboardButton("➕ Добавить недостающие данные",
                                     callback_data=f"medit_add_{order_id}"))
    m.add(types.InlineKeyboardButton("💰 Рассчитать стоимость",
                                     callback_data=f"medit_calc_{order_id}"))
    m.add(types.InlineKeyboardButton("⬅️ К заявке", callback_data=f"view_order_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                           parse_mode='Markdown', reply_markup=m)


def show_edit_existing_menu(user_id, order_id, message_id=None):
    order = orders_db.get_order(order_id)
    if not order: return
    text = (f"📝 *Изменить существующие данные*\n\n"
            f"📄 Путевой: {order['waybill_number']}\n📅 Дата: {order['date']}\n"
            f"🚛 {order['car_model']} ({order['car_plate']})\n🚚 Прицеп: {order['trailer_info']}\n"
            f"📍 {order['loading_point']} → {order['unloading_point']}\n\nЧто изменить?")
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("📄 Путевой", callback_data=f"medit_field_{order_id}_waybill"),
          types.InlineKeyboardButton("📅 Дата", callback_data=f"medit_field_{order_id}_date"))
    m.add(types.InlineKeyboardButton("🚚 Прицеп", callback_data=f"medit_field_{order_id}_trailer"),
          types.InlineKeyboardButton("🔢 Машина", callback_data=f"medit_field_{order_id}_car"))
    m.add(types.InlineKeyboardButton("📍 Погрузка", callback_data=f"medit_field_{order_id}_loading"),
          types.InlineKeyboardButton("🏁 Разгрузка", callback_data=f"medit_field_{order_id}_unloading"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"medit_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                           parse_mode='Markdown', reply_markup=m)


def show_add_data_menu(user_id, order_id, message_id=None):
    order = orders_db.get_order(order_id)
    if not order: return
    cargos = orders_db.get_cargos(order_id)
    text = "➕ *Добавить недостающие данные*\n\nВыберите груз:\n"
    for i, c in enumerate(cargos, 1):
        text += (f"\n*{i}.* {c.get('cargo_name', '')[:30]}\n"
                 f"   Количество: {c.get('quantity', '') or '—'} | "
                 f"Мест: {c.get('places', '') or '—'}\n")
    m = types.InlineKeyboardMarkup(row_width=1)
    for i, c in enumerate(cargos):
        m.add(types.InlineKeyboardButton(f"📦 {i+1}. {c.get('cargo_name', '')[:25]}",
                                         callback_data=f"medit_addcargo_{order_id}_{i}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"medit_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                           parse_mode='Markdown', reply_markup=m)


def show_add_cargo_menu(user_id, order_id, index, message_id=None):
    cargos = orders_db.get_cargos(order_id)
    if index < 0 or index >= len(cargos): return
    c = cargos[index]
    text = (f"📦 *Груз {index+1}*\n\nНазвание: {c.get('cargo_name', '-')}\n"
            f"Масса: {c.get('cargo_qty', '-')}\n🔢 Количество: {c.get('quantity', '—')}\n"
            f"📦 Мест: {c.get('places', '—')}\n\nЧто добавить?")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🔢 Задать количество",
                                     callback_data=f"medit_set_qty_{order_id}_{index}"))
    m.add(types.InlineKeyboardButton("⚖️ Количество = массе",
                                     callback_data=f"medit_equal_{order_id}_{index}"))
    m.add(types.InlineKeyboardButton("📦 Количество мест",
                                     callback_data=f"medit_places_{order_id}_{index}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"medit_add_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                           parse_mode='Markdown', reply_markup=m)


def show_calc_menu(user_id, order_id, message_id=None):
    order = orders_db.get_order(order_id)
    if not order: return
    cargos = orders_db.get_cargos(order_id)
    text = "💰 *Рассчитать стоимость*\n\nВыберите груз:\n"
    for i, c in enumerate(cargos, 1):
        text += (f"\n*{i}.* {c.get('cargo_name', '')[:30]}\n"
                 f"   Цена: {c.get('price', '—')} | НДС: {c.get('vat_rate', '—')} | "
                 f"С НДС: {c.get('total_with_vat', '—')}\n")
    if order.get('total_cost'):
        text += f"\n💰 *Итого без НДС:* {order['total_cost']} руб.\n"
    if order.get('total_with_vat'):
        text += f"💰 *Итого с НДС:* {order['total_with_vat']} руб.\n"
    m = types.InlineKeyboardMarkup(row_width=1)
    for i, c in enumerate(cargos):
        m.add(types.InlineKeyboardButton(f"💰 {i+1}. {c.get('cargo_name', '')[:25]}",
                                         callback_data=f"calc_cargo_{order_id}_{i}"))
    m.add(types.InlineKeyboardButton("📋 К заявке", callback_data=f"view_order_{order_id}"))
    m.add(types.InlineKeyboardButton("💰 К выбору груза", callback_data=f"medit_calc_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                           parse_mode='Markdown', reply_markup=m)


# =============================================================
# РОУТЕРЫ РЕДАКТИРОВАНИЯ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_')
                            and c.data.count('_') == 1)
def medit_back_to_main(call):
    show_master_edit_menu(call.message.chat.id,
                          int(call.data.replace('medit_', '')),
                          call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_existing_'))
def medit_existing_router(call):
    show_edit_existing_menu(call.message.chat.id,
                            int(call.data.replace('medit_existing_', '')),
                            call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_add_')
                            and not c.data.startswith('medit_addcargo_'))
def medit_add_router(call):
    show_add_data_menu(call.message.chat.id,
                       int(call.data.replace('medit_add_', '')),
                       call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_addcargo_'))
def medit_addcargo_router(call):
    rest = call.data.replace('medit_addcargo_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    show_add_cargo_menu(call.message.chat.id, order_id, index, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_calc_'))
def medit_calc_router(call):
    show_calc_menu(call.message.chat.id,
                   int(call.data.replace('medit_calc_', '')),
                   call.message.message_id)


# =============================================================
# РЕДАКТИРОВАНИЕ ПОЛЕЙ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_field_'))
def medit_field_router(call):
    user_id = call.message.chat.id
    rest = call.data.replace('medit_field_', '')
    parts = rest.rsplit('_', 1)
    if len(parts) != 2:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    try:
        order_id = int(parts[0])
    except ValueError:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    field = parts[1]
    order = orders_db.get_order(order_id)
    if not order: return
    master_edit_state[user_id] = {'order_id': order_id, 'field': field}
    back = types.InlineKeyboardMarkup(row_width=1)
    back.add(types.InlineKeyboardButton("⬅️ Назад",
                                        callback_data=f"medit_existing_{order_id}"))
    if field == 'waybill':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📄 Введите новый номер путевого:\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_field)
    elif field == 'date':
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("📅 Сегодня", callback_data=f"medit_date_{order_id}_today"),
              types.InlineKeyboardButton("📅 Вчера", callback_data=f"medit_date_{order_id}_yesterday"))
        m.add(types.InlineKeyboardButton("📅 Ввести вручную",
                                         callback_data=f"medit_date_{order_id}_manual"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"medit_existing_{order_id}"))
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📅 Выберите дату:", reply_markup=m)
    elif field == 'trailer':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🚚 Введите номер прицепа (или «-»):\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_field)
    elif field == 'car':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🔢 Введите марку и госномер:\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_field)
    elif field == 'loading':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📍 Введите пункт погрузки:\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_field)
    elif field == 'unloading':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🏁 Введите пункт разгрузки:\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_field)


def save_medit_field(message):
    user_id = message.chat.id
    if message.text and message.text.strip().lower() in ('/cancel', 'отмена'):
        state = master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Действие отменено.")
        if state and state.get('order_id'):
            show_master_edit_menu(user_id, state['order_id'])
        return
    state = master_edit_state.get(user_id)
    if not state:
        bot.send_message(user_id, "Сессия истекла."); return
    order_id = state['order_id']; field = state['field']; value = message.text.strip()
    field_map = {'waybill': 'waybill_number', 'trailer': 'trailer_info',
                 'loading': 'loading_point', 'unloading': 'unloading_point'}
    if field == 'car':
        parts = value.rsplit(' ', 1)
        if len(parts) == 2:
            orders_db.update_order_field(order_id, 'car_model', parts[0],
                                         actor_id=user_id)
            orders_db.update_order_field(order_id, 'car_plate', parts[1],
                                         actor_id=user_id)
        else:
            orders_db.update_order_field(order_id, 'car_model', value,
                                         actor_id=user_id)
    elif field in field_map:
        orders_db.update_order_field(order_id, field_map[field], value,
                                     actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            bot.send_message(user_id, "✅ Поле обновлено. Документ пересоздан:")
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Поле сохранено, но Word не пересоздан: {e}")
    master_edit_state.pop(user_id, None)
    show_edit_existing_menu(user_id, order_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_date_'))
def medit_date_router(call):
    user_id = call.message.chat.id
    rest = call.data.replace('medit_date_', '')
    parts = rest.rsplit('_', 1)
    if len(parts) != 2:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    try:
        order_id = int(parts[0])
    except ValueError:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    mode = parts[1]
    if mode == 'manual':
        master_edit_state[user_id] = {'order_id': order_id, 'field': 'date'}
        back = types.InlineKeyboardMarkup(row_width=1)
        back.add(types.InlineKeyboardButton("⬅️ Назад",
                                            callback_data=f"medit_existing_{order_id}"))
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📅 Введите дату *ДД.ММ.ГГ* (например, `06.10.26`):\n\n_Отмена: /cancel_",
                               parse_mode='Markdown', reply_markup=back)
        bot.register_next_step_handler_by_chat_id(user_id, save_medit_date_manual); return
    if mode == 'today':
        d = datetime.now()
    elif mode == 'yesterday':
        d = datetime.now() - timedelta(days=1)
    else:
        return
    orders_db.update_order_field(order_id, 'date', d.strftime("%d.%m.%y"),
                                 actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    show_edit_existing_menu(user_id, order_id, call.message.message_id)


def save_medit_date_manual(message):
    user_id = message.chat.id
    if message.text and message.text.strip().lower() in ('/cancel', 'отмена'):
        state = master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Действие отменено.")
        if state and state.get('order_id'):
            show_master_edit_menu(user_id, state['order_id'])
        return
    state = master_edit_state.get(user_id)
    if not state: return
    order_id = state['order_id']
    text = message.text.strip().replace('/', '.').replace('-', '.')
    date_obj = None
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            date_obj = datetime.strptime(text, fmt); break
        except ValueError:
            continue
    if not date_obj:
        bot.send_message(user_id,
                         "❌ Неверный формат. Введите *ДД.ММ.ГГ* или /cancel:",
                         parse_mode='Markdown')
        bot.register_next_step_handler(message, save_medit_date_manual); return
    orders_db.update_order_field(order_id, 'date', date_obj.strftime("%d.%m.%y"),
                                 actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    master_edit_state.pop(user_id, None)
    show_edit_existing_menu(user_id, order_id)


# =============================================================
# РЕДАКТИРОВАНИЕ ГРУЗА
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_set_qty_'))
def medit_set_qty(call):
    rest = call.data.replace('medit_set_qty_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    master_edit_state[call.message.chat.id] = {'order_id': order_id,
                                               'cargo_index': index,
                                               'action': 'set_qty'}
    back = types.InlineKeyboardMarkup(row_width=1)
    back.add(types.InlineKeyboardButton("⬅️ Назад",
                                        callback_data=f"medit_addcargo_{order_id}_{index}"))
    safe_edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                           text="🔢 Введите количество:\n\n_Отмена: /cancel_",
                           parse_mode='Markdown', reply_markup=back)
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, save_cargo_qty)


def save_cargo_qty(message):
    user_id = message.chat.id
    if message.text and message.text.strip().lower() in ('/cancel', 'отмена'):
        state = master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        if state and state.get('order_id'):
            show_master_edit_menu(user_id, state['order_id'])
        return
    state = master_edit_state.get(user_id)
    if not state:
        bot.send_message(user_id, "Сессия истекла."); return
    text = message.text.strip().replace(',', '.')
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число (или /cancel):")
        bot.register_next_step_handler(message, save_cargo_qty); return
    order_id = state['order_id']; index = state['cargo_index']
    cargos = orders_db.get_cargos(order_id)
    if index < len(cargos):
        cargos[index]['quantity'] = text.replace('.', ',')
        orders_db.save_cargos(order_id, cargos, actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    master_edit_state.pop(user_id, None)
    show_add_cargo_menu(user_id, order_id, index)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_equal_'))
def medit_equal(call):
    user_id = call.message.chat.id
    rest = call.data.replace('medit_equal_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    cargos = orders_db.get_cargos(order_id)
    if index < len(cargos):
        cargos[index]['quantity'] = cargos[index].get('cargo_qty', '')
        orders_db.save_cargos(order_id, cargos, actor_id=user_id)
    bot.answer_callback_query(call.id, "✅ Количество = масса")
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    show_add_cargo_menu(call.message.chat.id, order_id, index, call.message.message_id)


@bot.callback_query_handler(func=lambda c: (
    c.data.startswith('medit_places_')
    and not c.data.startswith('medit_places_nav_')
    and not c.data.startswith('medit_places_num_')
))
def medit_places_router(call):
    rest = call.data.replace('medit_places_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("Навал (нав.)",
                                     callback_data=f"medit_places_nav_{order_id}_{index}"),
          types.InlineKeyboardButton("Число",
                                     callback_data=f"medit_places_num_{order_id}_{index}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад",
                                     callback_data=f"medit_addcargo_{order_id}_{index}"))
    safe_edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                           text="📦 Выберите тип количества мест:", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_places_nav_'))
def medit_places_nav(call):
    user_id = call.message.chat.id
    rest = call.data.replace('medit_places_nav_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    cargos = orders_db.get_cargos(order_id)
    if index < len(cargos):
        cargos[index]['places'] = 'нав.'
        orders_db.save_cargos(order_id, cargos, actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    show_add_cargo_menu(call.message.chat.id, order_id, index, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('medit_places_num_'))
def medit_places_num(call):
    rest = call.data.replace('medit_places_num_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    master_edit_state[call.message.chat.id] = {'order_id': order_id,
                                               'cargo_index': index,
                                               'action': 'set_places'}
    back = types.InlineKeyboardMarkup(row_width=1)
    back.add(types.InlineKeyboardButton("⬅️ Назад",
                                        callback_data=f"medit_addcargo_{order_id}_{index}"))
    safe_edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                           text="📦 Введите число грузовых мест:\n\n_Отмена: /cancel_",
                           parse_mode='Markdown', reply_markup=back)
    bot.register_next_step_handler_by_chat_id(call.message.chat.id, save_cargo_places)


def save_cargo_places(message):
    user_id = message.chat.id
    if message.text and message.text.strip().lower() in ('/cancel', 'отмена'):
        state = master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        if state and state.get('order_id'):
            show_master_edit_menu(user_id, state['order_id'])
        return
    state = master_edit_state.get(user_id)
    if not state:
        bot.send_message(user_id, "Сессия истекла."); return
    try:
        num = int(message.text.strip())
    except ValueError:
        bot.send_message(user_id, "❌ Введите целое число (или /cancel):")
        bot.register_next_step_handler(message, save_cargo_places); return
    order_id = state['order_id']; index = state['cargo_index']
    cargos = orders_db.get_cargos(order_id)
    if index < len(cargos):
        cargos[index]['places'] = str(num)
        orders_db.save_cargos(order_id, cargos, actor_id=user_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id}")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    master_edit_state.pop(user_id, None)
    show_add_cargo_menu(user_id, order_id, index)


# =============================================================
# РАСЧЁТ СТОИМОСТИ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('calc_cargo_'))
def calc_cargo_router(call):
    rest = call.data.replace('calc_cargo_', '')
    order_id, index = parse_order_index(rest)
    if order_id is None:
        bot.answer_callback_query(call.id, "Ошибка данных."); return
    user_id = call.message.chat.id
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    cargos = orders_db.get_cargos(order_id)
    if index >= len(cargos):
        bot.answer_callback_query(call.id, "Груз не найден."); return
    master_edit_state[user_id] = {'order_id': order_id, 'cargo_index': index,
                                  'cargos': cargos, 'action': 'calc'}
    cargo = cargos[index]
    back = types.InlineKeyboardMarkup(row_width=1)
    back.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"medit_calc_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=(f"💰 *Расчёт для груза {index+1}*\n\n"
                                 f"📦 {cargo.get('cargo_name', '-')}\n"
                                 f"⚖️ Масса: {cargo.get('cargo_qty', '-')}\n\n"
                                 f"Введите *цену за единицу* (руб):\n\n_Отмена: /cancel_"),
                           parse_mode='Markdown', reply_markup=back)
    bot.register_next_step_handler_by_chat_id(user_id, save_master_price)


def save_master_price(message):
    user_id = message.chat.id
    if message.text and message.text.strip().lower() in ('/cancel', 'отмена'):
        state = master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        if state and state.get('order_id'):
            show_master_edit_menu(user_id, state['order_id'])
        return
    state = master_edit_state.get(user_id)
    if not state:
        bot.send_message(user_id, "Сессия истекла."); return
    text = message.text.strip().replace(',', '.').replace(' ', '')
    try:
        price = float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число (или /cancel):")
        bot.register_next_step_handler(message, save_master_price); return
    index = state['cargo_index']
    state['cargos'][index]['price'] = price
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("Без НДС", callback_data="master_vat_none"),
          types.InlineKeyboardButton("НДС 20%", callback_data="master_vat_20"))
    m.add(types.InlineKeyboardButton("⬅️ Назад",
                                     callback_data=f"calc_cargo_{state['order_id']}_{index}"))
    bot.send_message(user_id, f"💰 Цена: {price} руб.\n\nВыберите НДС:", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data in ('master_vat_none', 'master_vat_20'))
def save_master_vat(call):
    user_id = call.message.chat.id
    state = master_edit_state.get(user_id)
    if not state:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    index = state['cargo_index']; order_id = state['order_id']
    cargos = state['cargos']; cargo = cargos[index]
    try:
        qty = float(str(cargo.get('cargo_qty', '0')).replace(',', '.'))
    except Exception:
        qty = 0
    price = float(cargo.get('price', 0))
    total_cost = round(qty * price, 2)
    if call.data == 'master_vat_20':
        vat_rate = '20%'; vat_cost = round(total_cost * 0.20, 2)
    else:
        vat_rate = 'Без НДС'; vat_cost = 0.0
    total_with_vat = round(total_cost + vat_cost, 2)
    cargo['vat_rate'] = vat_rate; cargo['total_cost'] = total_cost
    cargo['vat_cost'] = vat_cost; cargo['total_with_vat'] = total_with_vat
    orders_db.save_cargos(order_id, cargos, actor_id=user_id)
    orders_db.recalculate_order_totals(order_id)
    try:
        merged = rebuild_word_from_order(order_id)
        if merged:
            with open(merged, 'rb') as f:
                bot.send_document(user_id, f, caption=f"📄 Заявка №{order_id} (обновлено)")
    except Exception as e:
        print(f"Ошибка Word: {e}")
    master_edit_state.pop(user_id, None)
    show_calc_menu(user_id, order_id, call.message.message_id)
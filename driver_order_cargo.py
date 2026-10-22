# =============================================================
# ВОДИТЕЛЬ: СТАНДАРТНЫЙ ГРУЗ (САМОСВАЛ)
# =============================================================
from config import bot, user_data
from utils import safe_edit_message_text, number_to_text
from keyboards import (get_cargo_type_keyboard, get_cargo_subcategory_keyboard,
                       get_cargo_distance_keyboard, get_unit_keyboard,
                       get_platform_categories_keyboard)
from database import CARS, CARGO_TYPES, CARGO_DISTANCES, UNITS
from driver_order_ui import show_cargos_menu, show_summary


# =============================================================
# СТАНДАРТНЫЙ ГРУЗ (САМОСВАЛ)
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('cargo_type::'))
def handle_cargo_type(call):
    user_id = call.message.chat.id
    cargo_id = call.data.replace('cargo_type::', '')
    if cargo_id not in CARGO_TYPES:
        bot.answer_callback_query(call.id, "Ошибка"); return
    cargo_info = CARGO_TYPES[cargo_id]
    user_data[user_id]['cargo_main'] = cargo_info['name']
    user_data[user_id]['cargo_id'] = cargo_id
    user_data[user_id]['cargo_sub'] = None
    user_data[user_id]['cargo_dist'] = None
    subs = cargo_info.get('subcategories') or {}
    if subs:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"✅ {cargo_info['name']}\n\nВыберите категорию:",
                               reply_markup=get_cargo_subcategory_keyboard(cargo_id))
    elif cargo_info.get('has_distance'):
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"✅ {cargo_info['name']}\n\nВыберите расстояние:",
                               reply_markup=get_cargo_distance_keyboard(cargo_id))
    else:
        finalize_cargo(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('cargo_sub::'))
def handle_cargo_subcategory(call):
    user_id = call.message.chat.id
    parts = call.data.replace('cargo_sub::', '').split('::')
    cargo_id, sub_id = parts[0], parts[1]
    cargo_info = CARGO_TYPES.get(cargo_id)
    if not cargo_info:
        bot.answer_callback_query(call.id, "Ошибка"); return
    subs = cargo_info.get('subcategories') or {}
    if sub_id not in subs:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['cargo_sub'] = subs[sub_id]
    if cargo_info.get('has_distance'):
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"✅ {subs[sub_id]}\n\nВыберите расстояние:",
                               reply_markup=get_cargo_distance_keyboard(cargo_id))
    else:
        finalize_cargo(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('cargo_dist::'))
def handle_cargo_distance(call):
    user_id = call.message.chat.id
    parts = call.data.replace('cargo_dist::', '').split('::')
    dist_id = parts[1]
    if dist_id not in CARGO_DISTANCES:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['cargo_dist'] = CARGO_DISTANCES[dist_id]
    finalize_cargo(user_id, call.message.message_id)


def finalize_cargo(user_id, message_id=None):
    main = user_data[user_id].get('cargo_main', '')
    sub = user_data[user_id].get('cargo_sub')
    dist = user_data[user_id].get('cargo_dist')
    parts = [sub if sub else main]
    if dist:
        parts.append(dist)
    cargo_name = ' '.join(parts)
    user_data[user_id]['temp_cargo_name'] = cargo_name
    msg = f"✅ Груз: {cargo_name}\n\nВведите количество рейсов:"
    if message_id:
        safe_edit_message_text(chat_id=user_id, message_id=message_id, text=msg)
    else:
        bot.send_message(user_id, msg)
    bot.register_next_step_handler_by_chat_id(user_id, get_trips)


def get_trips(message):
    user_id = message.chat.id
    text = (message.text or '').strip().replace(',', '.')
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число:")
        bot.register_next_step_handler(message, get_trips); return
    car_id = user_data[user_id].get('car_id')
    capacity = CARS.get(car_id, {}).get('capacity', 0)
    if capacity == 0:
        bot.send_message(user_id, "❌ Ошибка грузоподъёмности."); return
    total_weight = round(float(capacity) * float(text), 2)
    total_weight_str = (str(int(total_weight)) if total_weight == int(total_weight)
                        else f"{total_weight:.2f}".rstrip('0').rstrip('.').replace('.', ','))
    user_data[user_id]['temp_trips'] = text
    user_data[user_id]['temp_cargo_qty'] = total_weight_str
    user_data[user_id]['temp_total_mass_text'] = number_to_text(total_weight_str)
    cargo_name = user_data[user_id].get('temp_cargo_name', '')
    bot.send_message(user_id,
                     f"✅ {cargo_name}\n🚛 {CARS[car_id]['model']}\n🔢 {text}\n"
                     f"⚖️ {total_weight_str} т\n\nЕд. изм.:",
                     reply_markup=get_unit_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('unit::'))
def handle_unit_selection(call):
    user_id = call.message.chat.id
    unit_id = call.data.replace('unit::', '')
    if unit_id not in UNITS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    cargo = {
        'cargo_name': user_data[user_id].get('temp_cargo_name', ''),
        'unit': UNITS[unit_id],
        'cargo_qty': user_data[user_id].get('temp_cargo_qty', ''),
        'total_mass_text': user_data[user_id].get('temp_total_mass_text', ''),
        'trips': user_data[user_id].get('temp_trips', ''),
        'quantity': user_data[user_id].get('temp_cargo_qty', ''),
        'places': '', 'price': '', 'vat_rate': '', 'vat_cost': '',
        'total_cost': '', 'total_with_vat': '',
    }
    user_data[user_id].setdefault('cargos', []).append(cargo)
    for k in ['temp_cargo_name', 'temp_cargo_qty',
              'temp_total_mass_text', 'temp_trips']:
        user_data[user_id].pop(k, None)
    show_cargos_menu(user_id, call.message.message_id)



@bot.callback_query_handler(func=lambda c: c.data == 'add_more_cargo')
def add_more_cargo(call):
    user_id = call.message.chat.id
    car_type = user_data[user_id].get('car_type', 'tipper')
    for k in ['cargo_main', 'cargo_sub', 'cargo_dist', 'cargo_id',
              'temp_cargo_name', 'temp_trips', 'temp_cargo_qty',
              'temp_total_mass_text', 'temp_unit', 'temp_qty',
              'temp_places', 'temp_mass', 'temp_new_cargo_name']:
        user_data[user_id].pop(k, None)
    if not user_data[user_id].get('editing') and \
       len(user_data[user_id].get('cargos', [])) >= 15:
        bot.answer_callback_query(call.id, "Максимум 15 грузов!")
        return
    if car_type == 'platform':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🚜 Выберите *категорию следующего груза*:",
                               parse_mode='Markdown',
                               reply_markup=get_platform_categories_keyboard())
    else:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📦 Выберите тип груза:",
                               reply_markup=get_cargo_type_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'cargos_done')
def cargos_done(call):
    user_id = call.message.chat.id
    try:
        bot.delete_message(chat_id=user_id, message_id=call.message.message_id)
    except Exception:
        pass
    show_summary(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'back_to_qty')
def back_to_qty(call):
    user_id = call.message.chat.id
    cargo_name = user_data[user_id].get('temp_cargo_name', '')
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {cargo_name}\n\nВведите рейсы:")
    bot.register_next_step_handler_by_chat_id(user_id, get_trips)


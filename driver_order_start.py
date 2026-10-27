# =============================================================
# ВОДИТЕЛЬ: СТАРТ, ВЫБОР РЕЙСА, ДАТА, ПОГРУЗКА/РАЗГРУЗКА
# =============================================================
import copy
from telebot import types
from datetime import datetime, timedelta

from config import (bot, user_data, last_orders, pending_drivers,
                    YOUR_TELEGRAM_ID, save_last_orders)
from utils import safe_edit_message_text
from keyboards import (get_companies_keyboard, get_drivers_keyboard,
                       get_cars_keyboard, get_confirm_car_keyboard,
                       get_date_keyboard, get_trailer_keyboard,
                       get_loading_keyboard, get_unloading_keyboard,
                       get_cargo_type_keyboard, get_cargo_subcategory_keyboard,
                       get_platform_categories_keyboard)
from database import (COMPANIES, DRIVERS, CARS, TRAILERS, LOCATIONS,
                      CARGO_TYPES, trailer_number)
import orders_db
from driver_order_ui import show_summary


# =============================================================
# REPLY-КНОПКА "Я ВОДИТЕЛЬ" И РОЛЬ
# =============================================================
def handle_driver_button(message):
    user_id = message.chat.id
    if user_id in pending_drivers:
        bot.send_message(user_id,
                         "⏳ Ваша заявка на регистрацию рассматривается мастером.")
        return
    user_data[user_id] = {}
    if user_id in last_orders:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("📋 Мои заявки за месяц",
                                         callback_data="driver_month_orders"),
              types.InlineKeyboardButton("📋 Повторить прошлую заявку",
                                         callback_data="repeat_last_order"),
              types.InlineKeyboardButton("🆕 Новая заявка",
                                         callback_data="new_order"))
        bot.send_message(user_id, "👋 С возвращением!\n\nЧто будем делать?",
                         reply_markup=m)
    else:
        bot.send_message(user_id, "🏢 Выберите предприятие:",
                         reply_markup=get_companies_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'role_driver')
def handle_role_driver(call):
    user_id = call.message.chat.id
    if user_id in pending_drivers:
        safe_edit_message_text(chat_id=user_id,
                               message_id=call.message.message_id,
                               text="⏳ Ваша заявка на регистрацию рассматривается мастером.")
        return
    if user_id in last_orders:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("📋 Мои заявки за месяц",
                                         callback_data="driver_month_orders"),
              types.InlineKeyboardButton("📋 Повторить прошлую заявку",
                                         callback_data="repeat_last_order"),
              types.InlineKeyboardButton("🆕 Новая заявка",
                                         callback_data="new_order"))
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="👋 С возвращением!\n\nЧто будем делать?",
                               reply_markup=m)
    else:
        user_data[user_id] = {}
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🏢 Выберите предприятие:",
                               reply_markup=get_companies_keyboard())


# =============================================================
# ПОВТОРИТЬ / ИСТОРИЯ / НОВАЯ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'repeat_last_order')
def repeat_last_order(call):
    user_id = call.message.chat.id
    if user_id in last_orders:
        user_data[user_id] = copy.deepcopy(last_orders[user_id])
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
                               text="✏️ Что изменить в повторяемой заявке?",
                               parse_mode='Markdown', reply_markup=m)
    else:
        bot.answer_callback_query(call.id, "Нет сохранённой заявки")


@bot.callback_query_handler(func=lambda c: c.data == 'driver_month_orders')
def show_month_orders(call):
    user_id = call.message.chat.id
    orders = orders_db.get_driver_orders_current_month(user_id)
    if not orders:
        bot.answer_callback_query(call.id, "В этом месяце у вас пока нет заявок.")
        return
    m = types.InlineKeyboardMarkup(row_width=1)
    text = "📋 *Ваши заявки за этот месяц:*\n\n"
    for o in orders[:10]:
        text += (f"• {o['date']} • пут. {o['waybill_number']}\n"
                 f"  🚛 {o['car_model']} ({o['car_plate']})\n\n")
        m.add(types.InlineKeyboardButton(f"🔄 {o['date']} • {o['waybill_number']}",
                                         callback_data=f"repeat_hist_{o['id']}"))
    if len(orders) > 10:
        text += f"_...и ещё {len(orders) - 10}_\n"
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_menu"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('repeat_hist_'))
def repeat_hist(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('repeat_hist_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['driver_id']) != int(user_id):
        bot.answer_callback_query(call.id, "Ошибка доступа")
        return
    cargos = orders_db.get_cargos(order_id)
    date_parts = order['date'].split('.')
    user_data[user_id] = {
        'driver_name': order['driver_name'], 'car_id': '',
        'car_model': order['car_model'],
        'car_plate': order['car_plate'], 'trailer_info': order['trailer_info'],
        'waybill_number': order['waybill_number'],
        'day': date_parts[0], 'month': date_parts[1],
        'year': date_parts[2], 'loading_point': order['loading_point'],
        'unloading_point': order['unloading_point'],
        'shipper_handed_by': order['shipper_handed_by'],
        'consignee_received_by': order['consignee_received_by'],
        'cargos': copy.deepcopy(cargos), 'editing': True
    }
    for cid, c in CARS.items():
        if c['plate'] == order['car_plate']:
            user_data[user_id]['car_id'] = cid
            user_data[user_id]['car_type'] = c.get('type', 'tipper')
            break
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("📄 Путевой", callback_data="edit_waybill"),
          types.InlineKeyboardButton("📅 Дата", callback_data="edit_date"))
    m.add(types.InlineKeyboardButton("🚚 Прицеп", callback_data="edit_trailer"),
          types.InlineKeyboardButton("📍 Погрузка", callback_data="edit_loading"))
    m.add(types.InlineKeyboardButton("🏁 Разгрузка", callback_data="edit_unloading"),
          types.InlineKeyboardButton("📦 Грузы", callback_data="edit_cargos"))
    m.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_summary"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✏️ Что изменить в заявке от {order['date']}?",
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'new_order')
def new_order(call):
    user_id = call.message.chat.id
    user_data[user_id] = {}
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="🏢 Выберите предприятие:",
                           reply_markup=get_companies_keyboard())


# =============================================================
# ВЫБОР КОМПАНИИ / ВОДИТЕЛЯ / МАШИНЫ / ПРИЦЕПА
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('select_company_'))
def select_company(call):
    user_id = call.message.chat.id
    comp_id = call.data.replace('select_company_', '')
    if comp_id not in COMPANIES:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['company_id'] = comp_id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"🏢 {COMPANIES[comp_id]['name']}\n\n🚛 Выберите себя:",
                           reply_markup=get_drivers_keyboard(comp_id))


@bot.callback_query_handler(func=lambda c: c.data == 'back_to_companies')
def back_to_companies(call):
    user_id = call.message.chat.id
    user_data[user_id].pop('company_id', None)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="🏢 Выберите предприятие:",
                           reply_markup=get_companies_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('select_driver_'))
def handle_driver_selection(call):
    user_id = call.message.chat.id
    drv_id = call.data.replace('select_driver_', '')
    if drv_id not in DRIVERS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    driver = DRIVERS[drv_id]
    user_data[user_id]['driver_name'] = driver['name']
    car_id = driver.get('car_id')
    if car_id and car_id in CARS:
        car = CARS[car_id]
        user_data[user_id]['car_id'] = car_id
        user_data[user_id]['car_model'] = car['model']
        user_data[user_id]['car_plate'] = car['plate']
        user_data[user_id]['car_type'] = car.get('type', 'tipper')
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"👤 {driver['name']}\n\n🚛 {car['model']} ({car['plate']})\n\nОставить?",
                               reply_markup=get_confirm_car_keyboard())
    else:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"👤 {driver['name']}\n\nВыберите авто:",
                               reply_markup=get_cars_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'confirm_car_yes')
def handle_confirm_car_yes(call):
    data = user_data.get(call.message.chat.id, {})
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text=f"✅ {data.get('car_model', '-')} "
                                f"({data.get('car_plate', '-')})\n\nЕсть прицеп?",
                           reply_markup=get_trailer_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'confirm_car_no')
def handle_confirm_car_no(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🔄 Выберите авто:",
                           reply_markup=get_cars_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('select_car_'))
def handle_car_selection(call):
    user_id = call.message.chat.id
    car_id = call.data.replace('select_car_', '')
    if car_id not in CARS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['car_id'] = car_id
    user_data[user_id]['car_model'] = CARS[car_id]['model']
    user_data[user_id]['car_plate'] = CARS[car_id]['plate']
    user_data[user_id]['car_type'] = CARS[car_id].get('type', 'tipper')
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {CARS[car_id]['model']} ({CARS[car_id]['plate']})\n"
                                f"👤 {user_data[user_id].get('driver_name', '-')}\n\nЕсть прицеп?",
                           reply_markup=get_trailer_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'trailer_none')
def handle_trailer_none(call):
    user_id = call.message.chat.id
    user_data[user_id]['trailer_info'] = '-'
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="🚫 Без прицепа.\n\nВведите номер путевого листа:")
    bot.register_next_step_handler_by_chat_id(user_id, get_waybill_number)


@bot.callback_query_handler(func=lambda c: c.data.startswith('select_trailer_'))
def handle_trailer_selection(call):
    user_id = call.message.chat.id
    tr_id = call.data.replace('select_trailer_', '')
    if tr_id not in TRAILERS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    trailer = TRAILERS[tr_id]
    trailer_no = trailer_number(trailer)
    user_data[user_id]['trailer_info'] = trailer_no
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {trailer_no}\n\n"
                                f"Введите номер путевого листа:")
    bot.register_next_step_handler_by_chat_id(user_id, get_waybill_number)


# =============================================================
# ПУТЕВОЙ / ДАТА
# =============================================================
def get_waybill_number(message):
    user_id = message.chat.id
    text = (message.text or '').strip()
    if not text:
        bot.send_message(user_id, "❌ Введите номер путевого листа:")
        bot.register_next_step_handler_by_chat_id(user_id, get_waybill_number)
        return
    user_data[user_id]['waybill_number'] = text
    bot.send_message(user_id, "Выберите дату:", reply_markup=get_date_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'date_today')
def handle_date_today(call):
    user_id = call.message.chat.id
    t = datetime.now()
    user_data[user_id]['day'] = t.strftime("%d")
    user_data[user_id]['month'] = t.strftime("%m")
    user_data[user_id]['year'] = t.strftime("%y")
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {t.strftime('%d.%m.%y')}\n\nВыберите пункт погрузки:",
                           reply_markup=get_loading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'date_yesterday')
def handle_date_yesterday(call):
    user_id = call.message.chat.id
    d = datetime.now() - timedelta(days=1)
    user_data[user_id]['day'] = d.strftime("%d")
    user_data[user_id]['month'] = d.strftime("%m")
    user_data[user_id]['year'] = d.strftime("%y")
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {d.strftime('%d.%m.%y')}\n\nВыберите пункт погрузки:",
                           reply_markup=get_loading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'date_day_before')
def handle_date_day_before(call):
    user_id = call.message.chat.id
    d = datetime.now() - timedelta(days=2)
    user_data[user_id]['day'] = d.strftime("%d")
    user_data[user_id]['month'] = d.strftime("%m")
    user_data[user_id]['year'] = d.strftime("%y")
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {d.strftime('%d.%m.%y')}\n\nВыберите пункт погрузки:",
                           reply_markup=get_loading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'date_other')
def handle_date_other(call):
    user_id = call.message.chat.id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="📅 Введите дату *ДД.ММ.ГГ* (например, `06.10.26`):\n\n"
                                "_Можно и полный год: `06.10.2026`_",
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_custom_date)


def get_custom_date(message):
    user_id = message.chat.id
    text = (message.text or '').strip().replace('/', '.').replace('-', '.')
    date_obj = None
    for fmt in ("%d.%m.%y", "%d.%m.%Y"):
        try:
            date_obj = datetime.strptime(text, fmt); break
        except ValueError:
            continue
    if not date_obj:
        bot.send_message(user_id,
                         "❌ Неверный формат. Введите *ДД.ММ.ГГ* (например, `06.10.26`):",
                         parse_mode='Markdown')
        bot.register_next_step_handler(message, get_custom_date); return
    user_data[user_id]['day'] = date_obj.strftime("%d")
    user_data[user_id]['month'] = date_obj.strftime("%m")
    user_data[user_id]['year'] = date_obj.strftime("%y")
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    bot.send_message(user_id,
                     f"✅ {date_obj.strftime('%d.%m.%y')}\n\nВыберите пункт погрузки:",
                     reply_markup=get_loading_keyboard())


# =============================================================
# ПОГРУЗКА / РАЗГРУЗКА
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('loading_'))
def handle_loading_selection(call):
    user_id = call.message.chat.id
    loc_id = call.data.replace('loading_', '')
    if loc_id not in LOCATIONS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    loc_info = LOCATIONS[loc_id]
    user_data[user_id]['loading_point'] = loc_info['name']
    user_data[user_id]['shipper_handed_by'] = loc_info['master']
    if user_data[user_id].get('editing'):
        show_summary(user_id); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"✅ {loc_info['name']}\n\nВыберите пункт разгрузки:",
                           reply_markup=get_unloading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('unloading_'))
def handle_unloading_selection(call):
    user_id = call.message.chat.id
    loc_id = call.data.replace('unloading_', '')
    if loc_id not in LOCATIONS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    loc_info = LOCATIONS[loc_id]
    user_data[user_id]['unloading_point'] = loc_info['name']
    user_data[user_id]['consignee_received_by'] = loc_info['master']
    if user_data[user_id].get('editing'):
        show_summary(user_id); return

    for k in ['cargo_main', 'cargo_sub', 'cargo_dist', 'cargo_id',
              'temp_cargo_name', 'temp_trips', 'temp_cargo_qty',
              'temp_total_mass_text', 'temp_unit', 'temp_qty',
              'temp_places', 'temp_mass', 'temp_new_cargo_name']:
        user_data[user_id].pop(k, None)

    car_type = user_data[user_id].get('car_type', 'tipper')
    if car_type == 'platform':
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"✅ {loc_info['name']}\n\n"
                                    f"🚜 *Площадка (Трал)*\n\n"
                                    f"Выберите категорию груза:",
                               parse_mode='Markdown',
                               reply_markup=get_platform_categories_keyboard())
    else:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"✅ {loc_info['name']}\n\n📦 Выберите тип груза:",
                               reply_markup=get_cargo_type_keyboard())



# =============================================================
# НАВИГАЦИЯ НАЗАД
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'back_to_main_menu')
def back_to_main_menu(call):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🚛 Я водитель", callback_data="role_driver"),
          types.InlineKeyboardButton("👨‍💼 Я мастер", callback_data="role_master"))
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="👋 Выберите роль:", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'back_drivers')
def back_to_drivers(call):
    user_id = call.message.chat.id
    comp_id = user_data.get(user_id, {}).get('company_id')
    if comp_id and comp_id in COMPANIES:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text=f"🏢 {COMPANIES[comp_id]['name']}\n\n🚛 Выберите себя:",
                               reply_markup=get_drivers_keyboard(comp_id))
    else:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="🏢 Выберите предприятие:",
                               reply_markup=get_companies_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_cars')
def back_to_cars(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🔄 Авто:", reply_markup=get_cars_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_trailers')
def back_to_trailers(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🚚 Прицеп?", reply_markup=get_trailer_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_waybill')
def back_to_waybill(call):
    user_id = call.message.chat.id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="📄 Номер путевого:")
    bot.register_next_step_handler_by_chat_id(user_id, get_waybill_number)


@bot.callback_query_handler(func=lambda c: c.data == 'back_date')
def back_to_date(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="📅 Дата:", reply_markup=get_date_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_loading')
def back_to_loading(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="📍 Погрузка:", reply_markup=get_loading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_unloading')
def back_to_unloading(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="🏁 Разгрузка:", reply_markup=get_unloading_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'back_cargo_type')
def back_to_cargo_type(call):
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="📦 Тип груза:", reply_markup=get_cargo_type_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('back_to_sub::'))
def back_to_subcategory(call):
    cargo_id = call.data.replace('back_to_sub::', '')
    cargo_info = CARGO_TYPES.get(cargo_id, {})
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text=f"✅ {cargo_info.get('name', '')}\n\nКатегория:",
                           reply_markup=get_cargo_subcategory_keyboard(cargo_id))



# =============================================================
# ОТМЕНА / ОТЗЫВ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'cancel_order')
def cancel_order(call):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Да", callback_data="cancel_confirm"),
          types.InlineKeyboardButton("⬅️ Нет", callback_data="cancel_back"))
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="⚠️ Отменить заявку?",
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'cancel_confirm')
def cancel_confirm(call):
    user_id = call.message.chat.id
    user_data[user_id] = {}
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="❌ Заявка отменена.")
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🚛 Новая", callback_data="role_driver"))
    bot.send_message(user_id, "Что дальше?", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'cancel_back')
def cancel_back(call):
    show_summary(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == 'recall_order')
def recall_order(call):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Да", callback_data="recall_confirm"),
          types.InlineKeyboardButton("⬅️ Нет", callback_data="recall_cancel"))
    safe_edit_message_text(chat_id=call.message.chat.id,
                           message_id=call.message.message_id,
                           text="⚠️ Отозвать заявку?",
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'recall_confirm')
def recall_confirm(call):
    user_id = call.message.chat.id
    data = user_data.get(user_id, {})
    last_order = last_orders.get(user_id, {})
    order_ids = last_order.get('last_order_ids') or []
    if last_order.get('last_order_id') and last_order.get('last_order_id') not in order_ids:
        order_ids.append(last_order['last_order_id'])

    orders = []
    for order_id in order_ids:
        try:
            order = orders_db.get_order(int(order_id))
        except (TypeError, ValueError):
            order = None
        if order and not order.get('deleted_at') and int(order.get('driver_id') or 0) == int(user_id):
            orders.append(order)

    if not orders:
        bot.answer_callback_query(call.id, "Заявка не найдена или уже отозвана.")
        return

    if any(o.get('status') == 'printed' or o.get('ttn_number') for o in orders):
        bot.answer_callback_query(
            call.id, "⚠️ Заявка уже в реестре. Отзыв невозможен — обратитесь к мастеру.",
            show_alert=True)
        return

    deleted = []
    for order in orders:
        if orders_db.soft_delete_order(order['id'], user_id, reason='driver_recall'):
            deleted.append(order)
            try:
                bot.send_message(
                    int(order['master_id']),
                    f"🗑 Водитель отозвал заявку №{order['id']} "
                    f"(путевой {order.get('waybill_number', '-')}).")
            except Exception as e:
                print(f"⚠️ Не удалось уведомить мастера: {e}")

    try:
        bot.send_message(
            YOUR_TELEGRAM_ID,
            f"🗑 Водитель отозвал заявку(и): {', '.join(str(o['id']) for o in deleted)}\n"
            f"Водитель: {data.get('driver_name', '-')}\n"
            f"Путевой: {data.get('waybill_number', '-')}")
    except Exception as e:
        print(f"⚠️ Не удалось уведомить администратора: {e}")

    last_orders.setdefault(user_id, {}).pop('last_order_id', None)
    last_orders.setdefault(user_id, {}).pop('last_order_ids', None)
    save_last_orders()
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="✅ Заявка отозвана. Она сохранена в истории для аудита.")
    user_data[user_id] = {}
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("🚛 Новая", callback_data="role_driver"))
    bot.send_message(user_id, "Что дальше?", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'recall_cancel')
def recall_cancel(call):
    user_id = call.message.chat.id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="↩️ Оставляем.")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🗑 Отозвать", callback_data="recall_order"),
          types.InlineKeyboardButton("🔄 Ещё заявка", callback_data="role_driver"))
    bot.send_message(user_id, "Что дальше?", reply_markup=m)
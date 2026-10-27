# =============================================================
# РЕГИСТРАЦИЯ ВОДИТЕЛЯ (ВАРИАНТ А — с модерацией мастером)
# =============================================================
import copy
from telebot import types

from config import bot, user_data, pending_drivers, YOUR_TELEGRAM_ID
from database import (CARS, DRIVERS, TRAILERS, COMPANIES,
                      add_car, add_trailer, add_driver)
from keyboards import get_main_keyboard


# =============================================================
# СТАРТ РЕГИСТРАЦИИ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'reg_new_driver')
def reg_driver_start(call):
    user_id = call.message.chat.id
    if user_id in pending_drivers:
        bot.answer_callback_query(call.id, "⏳ Ваша заявка уже на рассмотрении."); return
    comp_id = user_data.get(user_id, {}).get('company_id')
    if not comp_id:
        bot.answer_callback_query(call.id, "Сначала выберите предприятие."); return
    user_data[user_id]['reg_driver'] = {'company_id': comp_id}
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            chat_id=user_id, message_id=call.message.message_id,
            text=(f"👤 *Регистрация нового водителя*\n\n"
                  f"🏢 Предприятие: {COMPANIES[comp_id]['name']}\n\n"
                  f"Шаг 1 из 4. Введите ваше *ФИО полностью* "
                  f"(например: Иванов Иван Иванович):\n\n"
                  f"_Отмена: /cancel_"),
            parse_mode='Markdown')
    except Exception:
        bot.send_message(user_id,
                         f"👤 Регистрация. Шаг 1 из 4. Введите ФИО полностью "
                         f"(например: Иванов Иван Иванович):")
    bot.register_next_step_handler_by_chat_id(user_id, reg_driver_name)


def reg_driver_name(message):
    user_id = message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.send_message(user_id, "Сессия регистрации истекла."); return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard()); return
    if len(text) < 5:
        bot.send_message(user_id, "❌ Слишком короткое ФИО. Введите полностью (или /cancel):")
        bot.register_next_step_handler(message, reg_driver_name); return
    st['name'] = text

    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🚫 Без машины (нет своей)", callback_data="reg_car_none"))
    for car_id, car_info in CARS.items():
        m.add(types.InlineKeyboardButton(f"{car_info['model']} ({car_info['plate']})",
                                         callback_data=f"reg_car_existing::{car_id}"))
    m.add(types.InlineKeyboardButton("➕ Добавить новую машину", callback_data="reg_car_new"))
    m.add(types.InlineKeyboardButton("❌ Отменить", callback_data="reg_cancel"))
    bot.send_message(user_id,
                     f"✅ ФИО: {text}\n\n"
                     f"Шаг 2 из 4. Выберите *машину* (если вашей нет — добавьте новую):",
                     parse_mode='Markdown', reply_markup=m)


# =============================================================
# ВЫБОР МАШИНЫ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data == 'reg_car_none')
def reg_driver_car_none(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    st['car_id'] = ""
    st['new_car'] = None
    bot.answer_callback_query(call.id, "🚫 Без машины")
    reg_driver_ask_trailer(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('reg_car_existing::'))
def reg_driver_car_existing(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    car_id = call.data.replace('reg_car_existing::', '')
    if car_id not in CARS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    st['car_id'] = car_id
    st['new_car'] = None
    bot.answer_callback_query(call.id, f"✅ {CARS[car_id]['model']}")
    reg_driver_ask_trailer(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'reg_car_new')
def reg_driver_car_new(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    st['new_car'] = {}
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            chat_id=user_id, message_id=call.message.message_id,
            text="🚛 *Новая машина*\n\nВведите *марку* (например: МАЗ 6501С5):\n\n_Отмена: /cancel_",
            parse_mode='Markdown')
    except Exception:
        bot.send_message(user_id, "🚛 Введите марку машины:")
    bot.register_next_step_handler_by_chat_id(user_id, reg_new_car_model)


def reg_new_car_model(message):
    user_id = message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st or st.get('new_car') is None:
        bot.send_message(user_id, "Сессия истекла."); return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard()); return
    if len(text) < 2:
        bot.send_message(user_id, "❌ Слишком короткая марка (или /cancel):")
        bot.register_next_step_handler(message, reg_new_car_model); return
    st['new_car']['model'] = text
    bot.send_message(user_id, "🔢 Введите *госномер* (например: А000АА-0):\n\n_Отмена: /cancel_",
                     parse_mode='Markdown')
    bot.register_next_step_handler(message, reg_new_car_plate)


def reg_new_car_plate(message):
    user_id = message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st or st.get('new_car') is None:
        bot.send_message(user_id, "Сессия истекла."); return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard()); return
    if len(text) < 3:
        bot.send_message(user_id, "❌ Слишком короткий номер (или /cancel):")
        bot.register_next_step_handler(message, reg_new_car_plate); return
    st['new_car']['plate'] = text
    bot.send_message(user_id, "⚖️ Введите *грузоподъёмность* в тоннах (например: 20.65):\n"
                              "Можно отправить «-» — по умолчанию 20.0:\n\n_Отмена: /cancel_",
                     parse_mode='Markdown')
    bot.register_next_step_handler(message, reg_new_car_capacity)


def reg_new_car_capacity(message):
    user_id = message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st or st.get('new_car') is None:
        bot.send_message(user_id, "Сессия истекла."); return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard()); return
    try:
        cap = 20.0 if text == '-' else float(text.replace(',', '.'))
    except ValueError:
        bot.send_message(user_id, "❌ Введите число или «-» (или /cancel):")
        bot.register_next_step_handler(message, reg_new_car_capacity); return
    st['new_car']['capacity'] = cap
    reg_driver_ask_trailer(user_id)


# =============================================================
# ПРИЦЕП (шаг 3)
# =============================================================
def reg_driver_ask_trailer(user_id, message_id=None):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🚫 Без прицепа / пропустить",
                                     callback_data="reg_trailer_none"))
    m.add(types.InlineKeyboardButton("➕ Добавить новый прицеп",
                                     callback_data="reg_trailer_new"))
    m.add(types.InlineKeyboardButton("❌ Отменить регистрацию",
                                     callback_data="reg_cancel"))
    text = ("📦 Шаг 3 из 4.\n\n"
            "Если вы ездите с прицепом, которого ещё нет в списке — добавьте его сейчас.\n"
            "Если прицепа нет или он уже есть в списке — пропустите этот шаг.")
    if message_id:
        try:
            bot.edit_message_text(chat_id=user_id, message_id=message_id,
                                  text=text, reply_markup=m)
            return
        except Exception:
            pass
    bot.send_message(user_id, text, reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'reg_trailer_none')
def reg_driver_trailer_none(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    st['new_trailer'] = None
    bot.answer_callback_query(call.id)
    reg_driver_finish(user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'reg_trailer_new')
def reg_driver_trailer_new(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return
    st['new_trailer'] = {}
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(
            chat_id=user_id, message_id=call.message.message_id,
            text="🚚 *Новый прицеп*\n\nВведите *номер* прицепа "
                 "(например: АА 8760-4):\n\n_Отмена: /cancel_",
            parse_mode='Markdown')
    except Exception:
        bot.send_message(user_id, "🚚 Введите номер прицепа:")
    bot.register_next_step_handler_by_chat_id(user_id, reg_new_trailer_plate)


def reg_new_trailer_plate(message):
    user_id = message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st or st.get('new_trailer') is None:
        bot.send_message(user_id, "Сессия истекла."); return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id].pop('reg_driver', None)
        bot.send_message(user_id, "❌ Регистрация отменена.",
                         reply_markup=get_main_keyboard()); return
    if len(text) < 3:
        bot.send_message(user_id, "❌ Слишком короткий номер (или /cancel):")
        bot.register_next_step_handler(message, reg_new_trailer_plate); return
    st['new_trailer']['plate'] = text
    reg_driver_finish(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'reg_cancel')
def reg_driver_cancel(call):
    user_id = call.message.chat.id
    user_data[user_id].pop('reg_driver', None)
    bot.answer_callback_query(call.id, "❌ Отменено")
    try:
        bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                              text="❌ Регистрация отменена.")
    except Exception:
        pass
    bot.send_message(user_id, "Для возврата в меню отправьте /start",
                     reply_markup=get_main_keyboard())


# =============================================================
# ШАГ 4 — ПРЕДПРОСМОТР И ОТПРАВКА МАСТЕРУ
# =============================================================
def reg_driver_finish(user_id, message_id=None):
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.send_message(user_id, "Сессия истекла."); return

    comp_name = COMPANIES.get(st['company_id'], {}).get('name', '—')

    if st.get('new_car') is not None and st['new_car'].get('model'):
        car_str = (f"🆕 {st['new_car']['model']} "
                   f"({st['new_car']['plate']}) — {st['new_car']['capacity']} т")
    elif st.get('car_id'):
        c = CARS.get(st['car_id'], {})
        car_str = f"{c.get('model','—')} ({c.get('plate','—')})"
    else:
        car_str = "🚫 без машины"

    if st.get('new_trailer') is not None and st['new_trailer'].get('plate'):
        trailer_str = f"🆕 {st['new_trailer']['plate']}"
    else:
        trailer_str = "—"

    text = (f"📝 *Проверьте данные регистрации*\n\n"
            f"👤 ФИО: {st['name']}\n"
            f"🏢 Предприятие: {comp_name}\n"
            f"🚛 Машина: {car_str}\n"
            f"🚚 Прицеп (новый в базе): {trailer_str}\n\n"
            f"Шаг 4 из 4. Отправляем мастеру на подтверждение?")
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Отправить", callback_data="reg_submit"),
          types.InlineKeyboardButton("❌ Отменить", callback_data="reg_cancel"))
    if message_id:
        try:
            bot.edit_message_text(chat_id=user_id, message_id=message_id,
                                  text=text, parse_mode='Markdown', reply_markup=m)
            return
        except Exception:
            pass
    bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'reg_submit')
def reg_driver_submit(call):
    user_id = call.message.chat.id
    st = user_data.get(user_id, {}).get('reg_driver')
    if not st:
        bot.answer_callback_query(call.id, "Сессия истекла."); return

    pending_drivers[user_id] = copy.deepcopy(st)

    comp_name = COMPANIES.get(st['company_id'], {}).get('name', '—')

    if st.get('new_car') is not None and st['new_car'].get('model'):
        car_str = (f"🆕 *НОВАЯ* {st['new_car']['model']} "
                   f"({st['new_car']['plate']}) — {st['new_car']['capacity']} т")
    elif st.get('car_id'):
        c = CARS.get(st['car_id'], {})
        car_str = f"{c.get('model','—')} ({c.get('plate','—')})"
    else:
        car_str = "🚫 без машины"

    if st.get('new_trailer') is not None and st['new_trailer'].get('plate'):
        trailer_str = f"🆕 *НОВЫЙ* {st['new_trailer']['plate']}"
    else:
        trailer_str = "—"

    text = (f"📝 *Новый водитель на регистрацию*\n\n"
            f"👤 ФИО: {st['name']}\n"
            f"🏢 Предприятие: {comp_name}\n"
            f"🚛 Машина: {car_str}\n"
            f"🚚 Прицеп: {trailer_str}\n\n"
            f"🆔 `{user_id}`")
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Принять",
                                     callback_data=f"accept_driver_reg_{user_id}"),
          types.InlineKeyboardButton("❌ Отклонить",
                                     callback_data=f"reject_driver_reg_{user_id}"))

    try:
        bot.send_message(YOUR_TELEGRAM_ID, text, parse_mode='Markdown', reply_markup=m)
    except Exception as e:
        print(f"⚠️ Не отправить заявку мастеру: {e}")
        bot.answer_callback_query(call.id, "⚠️ Ошибка отправки. Попробуйте позже."); return

    user_data[user_id].pop('reg_driver', None)

    bot.answer_callback_query(call.id, "✅ Отправлено мастеру")
    try:
        bot.edit_message_text(
            chat_id=user_id, message_id=call.message.message_id,
            text="⏳ *Заявка отправлена мастеру*\n\n"
                 "Пожалуйста, подождите подтверждения. "
                 "Когда мастер примет заявку — вы сможете создавать путевые листы.",
            parse_mode='Markdown')
    except Exception:
        pass
    bot.send_message(user_id, "Для возврата отправьте /start",
                     reply_markup=get_main_keyboard())


# =============================================================
# ПРИЁМ / ОТКЛОНЕНИЕ МАСТЕРОМ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('accept_driver_reg_'))
def accept_driver_reg(call):
    if call.message.chat.id != YOUR_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⛔ Только администратор."); return
    driver_user_id = int(call.data.replace('accept_driver_reg_', ''))
    st = pending_drivers.get(driver_user_id)
    if not st:
        bot.answer_callback_query(call.id, "Заявка уже обработана."); return

    try:
        car_id = st.get('car_id') or ""
        if st.get('new_car') is not None and st['new_car'].get('model'):
            car_id = add_car(st['new_car']['model'],
                             st['new_car']['plate'],
                             st['new_car']['capacity'])
            print(f"✅ Создана машина {car_id}")
        if st.get('new_trailer') is not None and st['new_trailer'].get('plate'):
            tr_id = add_trailer(st['new_trailer']['plate'])
            print(f"✅ Создан прицеп {tr_id}")
        drv_id = add_driver(st['name'], car_id, st['company_id'])
        print(f"✅ Создан водитель {drv_id}")
    except Exception as e:
        print(f"❌ Ошибка регистрации водителя: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}"); return

    pending_drivers.pop(driver_user_id, None)
    try:
        bot.edit_message_text(chat_id=YOUR_TELEGRAM_ID, message_id=call.message.message_id,
                              text=f"✅ Водитель *{st['name']}* зарегистрирован.",
                              parse_mode='Markdown')
    except Exception:
        pass

    try:
        bot.send_message(driver_user_id,
                         f"✅ *Регистрация подтверждена!*\n\n"
                         f"👤 {st['name']}\n"
                         f"Теперь вы можете создавать путевые листы.\n\n"
                         f"Нажмите «🚛 Я водитель».",
                         parse_mode='Markdown', reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"⚠️ Не уведомить водителя: {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_driver_reg_'))
def reject_driver_reg(call):
    if call.message.chat.id != YOUR_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⛔ Только администратор."); return
    driver_user_id = int(call.data.replace('reject_driver_reg_', ''))
    st = pending_drivers.pop(driver_user_id, None)
    if not st:
        bot.answer_callback_query(call.id, "Заявка уже обработана."); return
    try:
        bot.edit_message_text(chat_id=YOUR_TELEGRAM_ID, message_id=call.message.message_id,
                              text=f"❌ Заявка водителя *{st['name']}* отклонена.",
                              parse_mode='Markdown')
    except Exception:
        pass
    try:
        bot.send_message(driver_user_id,
                         "❌ *Ваша заявка на регистрацию отклонена.*\n\n"
                         "Обратитесь к мастеру за уточнениями.",
                         parse_mode='Markdown')
    except Exception:
        pass
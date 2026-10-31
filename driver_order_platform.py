# =============================================================
# ВОДИТЕЛЬ: ГРУЗ ДЛЯ ПЛОЩАДКИ (ТРАЛ)
# =============================================================
from telebot import types

from config import bot, user_data, pending_platform_cargos, YOUR_TELEGRAM_ID
from utils import safe_edit_message_text
from keyboards import (get_main_keyboard, get_platform_cargos_keyboard,
                       get_platform_categories_keyboard,
                       get_platform_unit_keyboard,
                       get_platform_places_keyboard,
                       get_platform_new_cargo_category_keyboard)
from database import PLATFORM_CATEGORIES, PLATFORM_CARGOS, UNITS
from driver_order_ui import show_cargos_menu

from log_setup import get_logger

logger = get_logger(__name__)
PLATFORM_MASS_PROMPT = (
    "Введите *общую массу груза в тоннах* (например, 14.7):\n\n"
    "_Отмена: /cancel_"
)


# =============================================================
# ГРУЗ ДЛЯ ПЛОЩАДКИ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('p_cat::'))
def handle_platform_category(call):
    user_id = call.message.chat.id
    cat_id = call.data.replace('p_cat::', '')
    if cat_id not in PLATFORM_CATEGORIES:
        bot.answer_callback_query(call.id, "Ошибка"); return
    bot.answer_callback_query(call.id)
    cat_info = PLATFORM_CATEGORIES[cat_id]
    cat_name = f"{cat_info.get('icon', '📦')} {cat_info.get('name', '')}"
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"*{cat_name}*\n\nВыберите груз:",
                           parse_mode='Markdown',
                           reply_markup=get_platform_cargos_keyboard(cat_id))


@bot.callback_query_handler(func=lambda c: c.data == 'p_cargo_back_cats')
def handle_p_cargo_back_cats(call):
    user_id = call.message.chat.id
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="🚜 *Площадка (Трал)*\n\nВыберите категорию груза:",
                           parse_mode='Markdown',
                           reply_markup=get_platform_categories_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('p_cargo_name::'))
def handle_p_cargo_name(call):
    user_id = call.message.chat.id
    cid = call.data.replace('p_cargo_name::', '')
    if cid not in PLATFORM_CARGOS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['temp_cargo_name'] = PLATFORM_CARGOS[cid]['name']
    bot.answer_callback_query(call.id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"Груз: *{user_data[user_id]['temp_cargo_name']}*\n\n"
                                f"Выберите *единицу измерения*:",
                           parse_mode='Markdown',
                           reply_markup=get_platform_unit_keyboard())


@bot.callback_query_handler(func=lambda c: c.data == 'p_cargo_custom')
def handle_p_cargo_custom(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="🚜 Введите *название своего груза*:\n\n_Отмена: /cancel_",
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_cargo_name)


def get_platform_cargo_name(message):
    user_id = message.chat.id
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id] = {}
        bot.send_message(user_id, "❌ Отменено.", reply_markup=get_main_keyboard()); return
    if len(text) < 2:
        bot.send_message(user_id, "❌ Слишком короткое название (или /cancel):")
        bot.register_next_step_handler(message, get_platform_cargo_name); return

    user_data[user_id]['temp_new_cargo_name'] = text
    bot.send_message(user_id,
                     f"Груз: *{text}*\n\n"
                     f"К какой категории его отнести?",
                     parse_mode='Markdown',
                     reply_markup=get_platform_new_cargo_category_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('p_newcat::'))
def handle_p_newcat(call):
    user_id = call.message.chat.id
    cat_id = call.data.replace('p_newcat::', '')
    name = user_data[user_id].get('temp_new_cargo_name')
    if not name:
        bot.answer_callback_query(call.id, "Сессия истекла."); return

    user_data[user_id]['temp_cargo_name'] = name
    bot.answer_callback_query(call.id)

    cat_info = PLATFORM_CATEGORIES.get(cat_id, {})
    cat_label = f"{cat_info.get('icon', '📦')} {cat_info.get('name', '—')}"

    try:
        msg = bot.send_message(
            YOUR_TELEGRAM_ID,
            f"📦 *Новый груз (Трал) на модерацию:*\n\n"
            f"Название: {name}\n"
            f"Категория: {cat_label}",
            parse_mode='Markdown',
        )
        pending_platform_cargos[msg.message_id] = {"name": name, "category": cat_id}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Добавить",
                callback_data=f"appr_pcargo::{cat_id}::{msg.message_id}"
            ),
            types.InlineKeyboardButton(
                "❌ Отклонить",
                callback_data=f"rej_pcargo::{msg.message_id}"
            )
        )
        bot.edit_message_reply_markup(chat_id=YOUR_TELEGRAM_ID,
                                      message_id=msg.message_id,
                                      reply_markup=markup)
    except Exception as e:
        logger.exception(f"⚠️ Не удалось отправить заявку на модерацию: {e}")

    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"Груз: *{name}*\n\n"
                                f"Выберите *единицу измерения*:",
                           parse_mode='Markdown',
                           reply_markup=get_platform_unit_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith('p_unit::'))
def handle_platform_unit(call):
    user_id = call.message.chat.id
    unit_id = call.data.replace('p_unit::', '')
    if unit_id not in UNITS:
        bot.answer_callback_query(call.id, "Ошибка"); return
    user_data[user_id]['temp_unit'] = UNITS[unit_id]
    bot.answer_callback_query(call.id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=f"Единица: {UNITS[unit_id]}\n\n"
                                f"Введите *количество* (число):\n\n_Отмена: /cancel_",
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_cargo_qty)


def get_platform_cargo_qty(message):
    user_id = message.chat.id
    text = (message.text or '').strip().replace(',', '.')
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id] = {}
        bot.send_message(user_id, "❌ Отменено.", reply_markup=get_main_keyboard()); return
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите число (например, 2.5) или /cancel:")
        bot.register_next_step_handler_by_chat_id(user_id, get_platform_cargo_qty)
        return
    user_data[user_id]['temp_qty'] = text
    bot.send_message(user_id,
                     "Выберите *количество грузовых мест*:",
                     parse_mode='Markdown',
                     reply_markup=get_platform_places_keyboard())
    # Пользователь может как нажать кнопку, так и сразу написать число.
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_places)


@bot.callback_query_handler(func=lambda c: c.data == 'p_places_num')
def handle_p_places_num(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    bot.clear_step_handler_by_chat_id(user_id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="Введите *количество грузовых мест* (число):\n\n_Отмена: /cancel_",
                           parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_places)


@bot.callback_query_handler(func=lambda c: c.data == 'p_places_nav')
def handle_p_places_nav(call):
    user_id = call.message.chat.id
    user_data.setdefault(user_id, {})['temp_places'] = 'нав.'
    bot.answer_callback_query(call.id, "Навал")
    bot.clear_step_handler_by_chat_id(user_id)
    safe_edit_message_text(
        chat_id=user_id, message_id=call.message.message_id,
        text="Количество мест: *нав.* (навал)\n\n" + PLATFORM_MASS_PROMPT,
        parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_mass)


def get_platform_places(message):
    user_id = message.chat.id
    text = (message.text or '').strip()
    normalized = text.lower().replace('.', '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id] = {}
        bot.send_message(user_id, "❌ Отменено.", reply_markup=get_main_keyboard()); return
    if normalized in ('нав', 'навал'):
        user_data[user_id]['temp_places'] = 'нав.'
        bot.send_message(user_id, PLATFORM_MASS_PROMPT, parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(user_id, get_platform_mass)
        return
    try:
        int(text)
    except ValueError:
        bot.send_message(user_id,
                         "❌ Введите целое число (например, 11), «навал» или /cancel:")
        bot.register_next_step_handler_by_chat_id(user_id, get_platform_places)
        return
    user_data[user_id]['temp_places'] = text
    bot.send_message(user_id, PLATFORM_MASS_PROMPT, parse_mode='Markdown')
    bot.register_next_step_handler_by_chat_id(user_id, get_platform_mass)


def get_platform_mass(message):
    user_id = message.chat.id
    text = (message.text or '').strip().replace(',', '.')
    if text.lower() in ('/cancel', 'отмена'):
        user_data[user_id] = {}
        bot.send_message(user_id, "❌ Отменено.", reply_markup=get_main_keyboard()); return
    try:
        float(text)
    except ValueError:
        bot.send_message(user_id, "❌ Введите массу числом (например, 14.7) или /cancel:")
        bot.register_next_step_handler_by_chat_id(user_id, get_platform_mass)
        return
    user_data[user_id]['temp_mass'] = text
    finish_platform_cargo(user_id)


def finish_platform_cargo(user_id):
    cargo = {
        'cargo_name': user_data[user_id].get('temp_cargo_name', ''),
        'unit': user_data[user_id].get('temp_unit', ''),
        'quantity': user_data[user_id].get('temp_qty', ''),
        'places': user_data[user_id].get('temp_places', ''),
        'cargo_qty': user_data[user_id].get('temp_mass', '0'),
        'trips': '-',
        'price': '', 'vat_rate': '', 'vat_cost': '',
        'total_cost': '', 'total_with_vat': '',
    }
    user_data[user_id].setdefault('cargos', []).append(cargo)
    for k in ['temp_cargo_name', 'temp_unit', 'temp_qty', 'temp_places',
              'temp_mass', 'temp_new_cargo_name']:
        user_data[user_id].pop(k, None)
    bot.send_message(user_id, "✅ Груз добавлен.")
    show_cargos_menu(user_id)


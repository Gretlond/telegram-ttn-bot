# =============================================================
# ВОДИТЕЛЬ: ОБЩИЕ ЭКРАНЫ (ГРУЗЫ, СВОДКА, СПИСОК РЕДАКТИРОВАНИЯ)
# =============================================================
from telebot import types

from config import bot, user_data
from utils import safe_edit_message_text


# =============================================================
# МЕНЮ ГРУЗОВ, СВОДКА И ПОДТВЕРЖДЕНИЕ
# =============================================================
def show_cargos_menu(user_id, message_id=None):
    cargos = user_data[user_id].get('cargos', [])
    text = "📦 *Грузы:*\n"
    for i, c in enumerate(cargos, 1):
        text += (f"\n*{i}.* {c['cargo_name']}\n"
                 f"   Рейсов: {c.get('trips', '-')}, Ед.: {c.get('unit', '-')}, "
                 f"Кол-во: {c.get('quantity', c.get('cargo_qty'))}\n")
        if c.get('places'):
            text += f"   Мест: {c.get('places')}\n"
        if c.get('cargo_qty') and c.get('unit') != 'тн':
            text += f"   Масса: {c.get('cargo_qty')} т\n"
    text += "\nЧто дальше?"
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("➕ Ещё груз", callback_data="add_more_cargo"),
          types.InlineKeyboardButton("✅ Продолжить", callback_data="cargos_done"))
    m.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_order"))
    if message_id:
        safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                               parse_mode='Markdown', reply_markup=m)
    else:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)


def show_summary(user_id):
    data = user_data.get(user_id, {})
    cargos = data.get('cargos', [])
    summary = (f"📋 *Проверьте заявку:*\n\n"
               f"📄 Путевой лист: {data.get('waybill_number', '-')}\n"
               f"📅 Дата: {data.get('day', '-')}.{data.get('month', '-')}.{data.get('year', '-')}\n"
               f"👤 Водитель: {data.get('driver_name', '-')}\n"
               f"🚛 {data.get('car_model', '-')} ({data.get('car_plate', '-')})\n"
               f"🚚 Прицеп: {data.get('trailer_info', '-')}\n"
               f"📍 Погрузка: {data.get('loading_point', '-')}\n"
               f"🏁 Разгрузка: {data.get('unloading_point', '-')}\n")
    if cargos:
        summary += "\n📦 *Грузы:*\n"
        for i, c in enumerate(cargos, 1):
            summary += (f"\n*{i}.* {c['cargo_name']}\n"
                        f"   Рейсов: {c.get('trips', '-')}, Ед.: {c.get('unit', '-')}, "
                        f"Кол-во: {c.get('quantity', c.get('cargo_qty'))}\n")
    else:
        summary += "\n❌ *Нет грузов*\n"
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("➕ Груз", callback_data="add_more_cargo"),
          types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order"))
    m.add(types.InlineKeyboardButton("✏️ Изменить", callback_data="edit_order"),
          types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_order"))
    bot.send_message(user_id, summary, parse_mode='Markdown', reply_markup=m)

def show_edit_cargos_list(user_id, message_id=None):
    cargos = user_data[user_id].get('cargos', [])
    if not cargos:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("➕ Добавить груз", callback_data="add_more_cargo"),
              types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_summary"))
        safe_edit_message_text(chat_id=user_id, message_id=message_id,
                               text="📦 *Грузы*\n\n_Список пуст._",
                               parse_mode='Markdown', reply_markup=m)
        return
    text = "📦 *Грузы*\n\nВыберите груз для изменения:\n\n"
    m = types.InlineKeyboardMarkup(row_width=1)
    for i, c in enumerate(cargos):
        text += (f"*{i + 1}.* {c['cargo_name']}\n"
                 f"   🔢 Рейсов: {c.get('trips', '-')} • "
                 f"⚖️ Масса: {c.get('cargo_qty', '-')} {c.get('unit', '')}\n\n")
        m.add(types.InlineKeyboardButton(f"📦 {i + 1}. {c['cargo_name'][:30]}",
                                         callback_data=f"edit_cargo_{i}"))
    m.add(types.InlineKeyboardButton("➕ Добавить груз", callback_data="add_more_cargo"))
    m.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_summary"))
    if message_id:
        safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                               parse_mode='Markdown', reply_markup=m)
    else:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)

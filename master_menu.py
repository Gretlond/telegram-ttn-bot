# =============================================================
# КАБИНЕТ МАСТЕРА, РЕГИСТРАЦИЯ МАСТЕРОВ, ПРОСМОТР ЗАЯВОК
# =============================================================
from telebot import types
import os
from datetime import datetime

from config import bot, MASTERS, pending_masters, YOUR_TELEGRAM_ID, save_masters, last_orders
from utils import (safe_edit_message_text, status_ru, strip_driver_prefix,
                   number_to_text, calculate_total_places_text_master,
                   calculate_vat_totals, amount_to_words_parts)
from keyboards import get_main_keyboard
from word_filler import fill_documents, convert_to_pdf
import orders_db


# =============================================================
# РОЛЬ МАСТЕРА / ВХОД
# =============================================================
def handle_master_button(message):
    user_id = message.chat.id
    if user_id in MASTERS:
        show_master_menu(user_id); return
    if user_id in pending_masters:
        bot.send_message(user_id, "⏳ Ваша заявка на регистрацию ещё не подтверждена."); return
    m = types.InlineKeyboardMarkup(row_width=1)
    for m_id, m_info in MASTERS.items():
        m.add(types.InlineKeyboardButton(f"👤 {m_info['name']}",
                                         callback_data=f"master_login_{m_id}"))
    m.add(types.InlineKeyboardButton("➕ Зарегистрироваться", callback_data="master_register"))
    bot.send_message(user_id,
                     "👨‍💼 Выберите себя из списка:\n\n_Если вас нет — нажмите «Зарегистрироваться»._",
                     parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'role_master')
def handle_role_master(call):
    user_id = call.message.chat.id
    if user_id in MASTERS:
        show_master_menu(user_id, call.message.message_id); return
    if user_id in pending_masters:
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="⏳ Ваша заявка на регистрацию ещё не подтверждена."); return
    m = types.InlineKeyboardMarkup(row_width=1)
    for m_id, m_info in MASTERS.items():
        m.add(types.InlineKeyboardButton(f"👤 {m_info['name']}",
                                         callback_data=f"master_login_{m_id}"))
    m.add(types.InlineKeyboardButton("➕ Зарегистрироваться", callback_data="master_register"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_menu"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="👨‍💼 Выберите себя:\n\n_Если вас нет — нажмите «Зарегистрироваться»._",
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('master_login_'))
def master_login(call):
    master_id = int(call.data.replace('master_login_', ''))
    if call.message.chat.id != master_id:
        bot.answer_callback_query(call.id, "⛔ Это чужой аккаунт!", show_alert=True); return
    show_master_menu(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_register')
def master_register(call):
    user_id = call.message.chat.id
    if user_id in MASTERS:
        bot.answer_callback_query(call.id, "✅ Вы уже зарегистрированы!"); return
    if user_id in pending_masters:
        bot.answer_callback_query(call.id, "⏳ Заявка уже на рассмотрении."); return
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="📝 Введите ваше ФИО (например, Иванов И.И.):")
    bot.register_next_step_handler_by_chat_id(user_id, register_master_name)


def register_master_name(message):
    user_id = message.chat.id
    name = message.text.strip()
    if not name or len(name) < 3:
        bot.send_message(user_id, "❌ Введите корректное ФИО:")
        bot.register_next_step_handler(message, register_master_name); return
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_master_{user_id}"),
          types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_master_{user_id}"))
    bot.send_message(YOUR_TELEGRAM_ID,
                     f"📝 *Заявка на регистрацию мастера*\n\n👤 {name}\n🆔 `{user_id}`",
                     parse_mode='Markdown', reply_markup=m)
    pending_masters[user_id] = {"name": name}
    bot.send_message(user_id, "⏳ Заявка отправлена администратору.")


@bot.callback_query_handler(func=lambda c: c.data.startswith('accept_master_'))
def accept_master(call):
    if call.message.chat.id != YOUR_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⛔ Только администратор."); return
    master_id = int(call.data.replace('accept_master_', ''))
    if master_id not in pending_masters:
        bot.answer_callback_query(call.id, "Заявка уже обработана."); return
    master = pending_masters.pop(master_id)
    MASTERS[master_id] = {"name": master['name'], "locations": []}
    save_masters()
    safe_edit_message_text(chat_id=YOUR_TELEGRAM_ID, message_id=call.message.message_id,
                           text=f"✅ Мастер *{master['name']}* зарегистрирован.",
                           parse_mode='Markdown')
    try:
        bot.send_message(master_id,
                         f"✅ Регистрация подтверждена!\n👤 {master['name']}\n\nОтправьте /start")
    except Exception as e:
        print(f"Не уведомить: {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_master_'))
def reject_master(call):
    if call.message.chat.id != YOUR_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⛔ Только администратор."); return
    master_id = int(call.data.replace('reject_master_', ''))
    if master_id not in pending_masters:
        bot.answer_callback_query(call.id, "Заявка обработана."); return
    pending_masters.pop(master_id)
    safe_edit_message_text(chat_id=YOUR_TELEGRAM_ID, message_id=call.message.message_id,
                           text="❌ Заявка отклонена.", parse_mode='Markdown')
    try:
        bot.send_message(master_id, "❌ Ваша заявка отклонена.")
    except Exception:
        pass


# =============================================================
# КАБИНЕТ МАСТЕРА
# =============================================================
def show_master_menu(user_id, message_id=None):
    master = MASTERS.get(user_id, {})
    name = master.get('name', 'Мастер')
    text = (f"👨‍💼 *Кабинет мастера*\n\n👤 Имя: {name}\n🆔 ID: `{user_id}`\n\n"
            f"📋 *Функции:*\n• Просмотр заявок\n• Редактирование заявок\n"
            f"• Расчёт стоимости\n• Печать PDF\n\n_Для выхода напишите /start_")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📋 Мои заявки", callback_data="master_orders"))
    m.add(types.InlineKeyboardButton("📦 Текущий реестр", callback_data="master_registry"))
    try:
        is_admin = int(user_id) == int(YOUR_TELEGRAM_ID)
    except (TypeError, ValueError):
        is_admin = False
    if is_admin:
        m.add(types.InlineKeyboardButton("⚙️ Управление", callback_data="adm_menu"))
    m.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="master_refresh"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_menu"))
    if message_id:
        try:
            safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                                   parse_mode='Markdown', reply_markup=m)
        except Exception:
            bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)
    else:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_refresh')
def master_refresh(call):
    show_master_menu(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_orders')
def master_orders(call):
    user_id = call.message.chat.id
    all_orders = orders_db.get_master_orders(int(user_id))
    new_orders = [o for o in all_orders if o['status'] in ('new', 'confirmed')]
    printed_orders = [o for o in all_orders if o['status'] == 'printed']
    archived_orders = [o for o in all_orders if o['status'] == 'archived']
    history_count = len(printed_orders) + len(archived_orders)

    if not all_orders:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📋 У вас пока нет заявок.", reply_markup=m); return

    text = f"📋 *Мои заявки* — не распечатано: {len(new_orders)}\n\n"
    m = types.InlineKeyboardMarkup(row_width=1)
    if new_orders:
        text += "🆕 *НЕ РАСПЕЧАТАННЫЕ:*\n\n"
        for o in new_orders[:20]:
            text += (f"*№{o['id']}* • {o['date']} • пут. {o['waybill_number']}\n"
                     f"   🚛 {o['car_model']} ({o['car_plate']})\n"
                     f"   📍 {o['loading_point']} → {o['unloading_point']}\n\n")
            m.add(types.InlineKeyboardButton(
                f"🆕 №{o['id']} • {o['date']} • {o['waybill_number']}",
                callback_data=f"view_order_{o['id']}"))
        if len(new_orders) > 20:
            text += f"_...и ещё {len(new_orders) - 20}_\n\n"
    else:
        text += "✅ _Все заявки распечатаны._\n\n"
    if history_count > 0:
        m.add(types.InlineKeyboardButton(f"📦 История ({history_count})",
                                         callback_data="master_history"))
    m.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="master_orders"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_history')
def master_history(call):
    user_id = call.message.chat.id
    all_orders = orders_db.get_master_orders(int(user_id))
    new_orders = [o for o in all_orders if o['status'] in ('new', 'confirmed')]
    printed_orders = [o for o in all_orders if o['status'] == 'printed']
    archived_orders = [o for o in all_orders if o['status'] == 'archived']

    if not printed_orders and not archived_orders:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("⬅️ К новым", callback_data="master_orders"))
        safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                               text="📦 История пуста.", reply_markup=m); return

    total = len(printed_orders) + len(archived_orders)
    text = f"📦 *История заявок* ({total})\n\n"
    m = types.InlineKeyboardMarkup(row_width=1)
    if printed_orders:
        text += "🖨 *Распечатанные:*\n\n"
        for o in printed_orders[:15]:
            ttn = o.get('ttn_number') or '—'
            text += (f"*№{o['id']}* • {o['date']} • ТТН №{ttn}\n"
                     f"   🚛 {o['car_model']} ({o['car_plate']})\n"
                     f"   📍 {o['loading_point']} → {o['unloading_point']}\n\n")
            m.add(types.InlineKeyboardButton(f"🖨 №{o['id']} • ТТН №{ttn}",
                                             callback_data=f"view_order_{o['id']}"))
        if len(printed_orders) > 15:
            text += f"_...и ещё {len(printed_orders) - 15}_\n\n"
    if archived_orders:
        text += "📦 *Архив:*\n\n"
        for o in archived_orders[:10]:
            text += f"*№{o['id']}* • {o['date']} • пут. {o['waybill_number']}\n"
            m.add(types.InlineKeyboardButton(f"📦 №{o['id']} • {o['date']}",
                                             callback_data=f"view_order_{o['id']}"))
    m.add(types.InlineKeyboardButton(
        f"🆕 К новым ({len(new_orders)})" if new_orders else "🆕 К новым",
        callback_data="master_orders"))
    m.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="master_history"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_back')
def master_back(call):
    show_master_menu(call.message.chat.id, call.message.message_id)


# =============================================================
# КАРТОЧКА ЗАЯВКИ
# =============================================================
def render_order_card(order_id, user_id, message_id=None):
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id): return
    if order.get('deleted_at'): return
    cargos = orders_db.get_cargos(order_id)
    ttn = order.get('ttn_number') or ''
    ttn_line = f"📄 ТТН №`{ttn}` (стр. {order.get('order_row', '?')})\n" if ttn else ""
    text = (f"📋 *Заявка №{order['id']}*\n\n"
            f"📄 Путевой лист: {order['waybill_number']}\n{ttn_line}"
            f"📅 Дата: {order['date']}\n🚛 {order['car_model']} ({order['car_plate']})\n"
            f"🚚 Прицеп: {order['trailer_info']}\n📍 Погрузка: {order['loading_point']}\n"
            f"🏁 Разгрузка: {order['unloading_point']}\n📊 Статус: {status_ru(order['status'])}\n\n")
    if cargos:
        text += "📦 *Грузы:*\n"
        for i, c in enumerate(cargos, 1):
            qd = c.get('quantity', '') or c.get('cargo_qty', '-')
            text += (f"\n*{i}.* {c.get('cargo_name', '-')}\n"
                     f"   Ед.: {c.get('unit', '-')}, Кол-во: {qd}, Масса: {c.get('cargo_qty', '-')}\n")
            if c.get('places'): text += f"   Мест: {c.get('places')}\n"
            if c.get('price'): text += f"   Цена: {c.get('price')} руб.\n"
            if c.get('vat_rate'): text += f"   НДС: {c.get('vat_rate')}\n"
            if c.get('total_cost'): text += f"   Стоимость: {c.get('total_cost')} руб.\n"
            if c.get('total_with_vat'): text += f"   С НДС: {c.get('total_with_vat')} руб.\n"
    if order.get('total_cost'):
        text += f"\n💰 *Итого без НДС:* {order['total_cost']} руб.\n"
    if order.get('total_with_vat'):
        text += f"💰 *Итого с НДС:* {order['total_with_vat']} руб.\n"

    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"medit_{order_id}"))
    m.add(types.InlineKeyboardButton("📄 Файлы для печати (Word + PDF)",
                                     callback_data=f"pdf_order_{order_id}"))
    if order['status'] == 'printed':
        m.add(types.InlineKeyboardButton("↩️ Отменить печать",
                                         callback_data=f"unprint_order_{order_id}"),
              types.InlineKeyboardButton("🗑 Убрать из реестра",
                                         callback_data=f"unreg_order_{order_id}"))
    else:
        print_label = "🖨 Повторно распечатана" if ttn else "🖨 Распечатана"
        m.add(types.InlineKeyboardButton(print_label,
                                         callback_data=f"print_order_{order_id}"))
        if ttn:
            m.add(types.InlineKeyboardButton("🗑 Убрать из реестра",
                                             callback_data=f"unreg_order_{order_id}"))
        else:
            m.add(types.InlineKeyboardButton("🗑 Удалить",
                                             callback_data=f"del_order_{order_id}"))
    m.add(types.InlineKeyboardButton("🕘 История заявки",
                                     callback_data=f"order_history_{order_id}"))
    m.add(types.InlineKeyboardButton("⬅️ К списку", callback_data="master_orders"))
    if message_id:
        safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                               parse_mode='Markdown', reply_markup=m)
    else:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('view_order_'))
def view_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('view_order_', ''))
    order = orders_db.get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "Заявка не найдена."); return
    if int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Это не ваша заявка.", show_alert=True); return
    if order.get('deleted_at'):
        bot.answer_callback_query(
            call.id, "🗑 Заявка удалена. Восстановить может администратор.", show_alert=True)
        return
    render_order_card(order_id, user_id, call.message.message_id)


# =============================================================
# PDF ЗАЯВКИ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('pdf_order_'))
def pdf_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('pdf_order_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    if order.get('deleted_at'):
        bot.answer_callback_query(call.id, "🗑 Заявка удалена."); return
    bot.answer_callback_query(call.id, "⏳ Готовлю файлы...")
    status_msg = bot.send_message(user_id, "⏳ Создаю документы...")
    try:
        merged_path = rebuild_word_from_order(order_id)
        if not merged_path:
            bot.edit_message_text(chat_id=user_id, message_id=status_msg.message_id,
                                  text="❌ Не удалось создать Word-документ."); return
        with open(merged_path, 'rb') as f:
            bot.send_document(user_id, f,
                caption=(f"📄 *Заявка №{order_id} — Word для печати*\n\n"
                         f"🖨 *Как печатать:*\n1. Откройте файл в Word\n"
                         f"2. Файл → Печать\n3. Выберите принтер\n4. По одной стороне\n"
                         f"5. Переверните лист, печать — вторая сторона\n\n"
                         f"После печати поставьте печать."),
                parse_mode='Markdown')
        success, result = convert_to_pdf(merged_path)
        if success:
            pdf_path = result
            try:
                with open(pdf_path, 'rb') as f:
                    bot.send_document(user_id, f,
                        caption=f"📄 *Заявка №{order_id} — PDF-версия*\n\nДля просмотра и архива.",
                        parse_mode='Markdown')
            except Exception as e:
                bot.send_message(user_id, f"⚠️ PDF создан, но не отправлен: {e}")
        else:
            bot.send_message(user_id, f"⚠️ PDF не создан: {result}")
        try:
            bot.delete_message(chat_id=user_id, message_id=status_msg.message_id)
        except Exception:
            pass
    except Exception as e:
        print(f"❌ Ошибка pdf_order: {e}")
        try:
            bot.edit_message_text(chat_id=user_id, message_id=status_msg.message_id,
                                  text=f"❌ Ошибка: {e}")
        except Exception:
            pass


def rebuild_word_from_order(order_id):
    order = orders_db.get_order(order_id)
    if not order: return None
    cargos = orders_db.get_cargos(order_id)
    date_parts = order['date'].split('.')
    driver_clean = strip_driver_prefix(order.get('driver_name', ''))
    cargo_accepted = f"Водитель {driver_clean}" if driver_clean else ''
    total_mass = 0.0
    for c in cargos:
        try:
            total_mass += float(str(c.get('cargo_qty', '0')).replace(',', '.'))
        except (ValueError, TypeError):
            pass
    if total_mass > 0:
        total_mass_str = str(int(total_mass)) if total_mass == int(total_mass) else \
            f"{total_mass:.2f}".rstrip('0').rstrip('.').replace('.', ',')
        total_mass_text = number_to_text(total_mass_str) + " тонн"
    else:
        total_mass_str = ''; total_mass_text = ''

    _, total_vat, total_with_vat = calculate_vat_totals(cargos)
    total_vat_text, total_vat_cents = amount_to_words_parts(total_vat)
    total_with_vat_text, total_with_vat_cents = amount_to_words_parts(total_with_vat)

    data = {
        'day': date_parts[0] if len(date_parts) > 0 else '',
        'month': date_parts[1] if len(date_parts) > 1 else '',
        'year': date_parts[2] if len(date_parts) > 2 else '',
        'waybill_number': order.get('waybill_number', ''),
        'car_model': order.get('car_model', ''),
        'car_plate': order.get('car_plate', ''),
        'trailer_info': order.get('trailer_info', '-'),
        'loading_point': order.get('loading_point', ''),
        'unloading_point': order.get('unloading_point', ''),
        'driver_name': driver_clean,
        'shipper_handed_by': order.get('shipper_handed_by', ''),
        'consignee_received_by': order.get('consignee_received_by', ''),
        'release_allowed_by': order.get('release_allowed_by', os.environ.get('RELEASE_ALLOWED_BY', 'Руководитель')),
        'cargo_accepted_by': cargo_accepted,
        'total_qty': total_mass_str,
        'total_mass_text': total_mass_text,
        'total_places_text': calculate_total_places_text_master(cargos),
        'total_vat_text': total_vat_text,
        'total_vat_cents': total_vat_cents,
        'total_with_vat_text': total_with_vat_text,
        'total_with_vat_cents': total_with_vat_cents,
        'cargos': cargos,
    }
    output_name = f"ТТН_{order['waybill_number']}_order{order['id']}"
    _, _, merged_path = fill_documents(data, output_name)
    return merged_path


@bot.callback_query_handler(func=lambda c: c.data.startswith('del_order_')
                            and not c.data.startswith(('del_order_confirm_',
                                                       'del_order_cancel_')))
def del_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('del_order_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    if order.get('deleted_at'):
        bot.answer_callback_query(call.id, "🗑 Заявка уже удалена."); return
    if order['status'] == 'printed' or order.get('ttn_number'):
        bot.answer_callback_query(
            call.id, "⚠️ Сначала отмените печать и уберите заявку из реестра.")
        return
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Да, удалить",
                                     callback_data=f"del_order_confirm_{order_id}"),
          types.InlineKeyboardButton("⬅️ Нет",
                                     callback_data=f"del_order_cancel_{order_id}"))
    safe_edit_message_text(
        chat_id=user_id, message_id=call.message.message_id,
        text=(f"⚠️ *Удалить заявку №{order_id}?*\n\n"
              f"Она исчезнет из списков, но останется в базе и журнале действий "
              f"для аудита.\n\nВосстановить можно через администратора."),
        parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('del_order_confirm_'))
def del_order_confirm(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('del_order_confirm_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    if order.get('deleted_at'):
        bot.answer_callback_query(call.id, "Заявка уже удалена.")
        master_orders(call); return
    if order['status'] == 'printed' or order.get('ttn_number'):
        bot.answer_callback_query(
            call.id, "⚠️ Сначала отмените печать и уберите заявку из реестра.")
        render_order_card(order_id, user_id, call.message.message_id); return
    if orders_db.soft_delete_order(order_id, user_id, reason='master_delete'):
        bot.answer_callback_query(call.id, f"🗑 Заявка №{order_id} удалена.")
    else:
        bot.answer_callback_query(call.id, "Заявка уже удалена.")
    master_orders(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith('del_order_cancel_'))
def del_order_cancel(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('del_order_cancel_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    render_order_card(order_id, user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('order_history_'))
def order_history(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('order_history_', ''))
    order = orders_db.get_order(order_id)
    if not order or int(order['master_id']) != int(user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа."); return
    events = orders_db.get_order_events(order_id, limit=30)
    from audit_format import format_events
    text = (f"🕘 История заявки №{order_id}\n\n"
            + (format_events(events) if events else "Событий пока нет."))
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("⬅️ К заявке",
                                     callback_data=f"view_order_{order_id}"))
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text=text, reply_markup=m)
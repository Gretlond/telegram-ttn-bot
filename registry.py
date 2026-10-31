# =============================================================
# РЕЕСТР ТТН
# =============================================================
from telebot import types
import os
from datetime import datetime

from config import bot, master_edit_state, MASTERS, REGISTRY_MASTER_NAME
from utils import safe_edit_message_text
from master_menu import show_master_menu
import orders_db
import registry_filler

from log_setup import get_logger

logger = get_logger(__name__)

# =============================================================
# ПЕЧАТЬ / ОТМЕНА ПЕЧАТИ
# =============================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith('print_order_'))
def print_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('print_order_', ''))
    order = orders_db.get_order(order_id)
    if not order or not orders_db.can_access_order(order, user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.")
        return
    if order.get('deleted_at'):
        bot.answer_callback_query(call.id, "🗑 Заявка удалена.")
        return
    if order.get('ttn_number'):
        # После «Отменить печать» ТТН остаётся за заявкой. Это позволяет
        # повторно отметить её распечатанной без дыры в реестре.
        if order.get('status') == 'printed':
            bot.answer_callback_query(call.id,
                                      f"⚠️ Уже в реестре: №{order['ttn_number']}")
            return
        orders_db.set_order_status(order_id, 'printed')
        orders_db.log_order_event(order_id, user_id, 'reprinted', {
            'ttn_number': order.get('ttn_number'),
            'order_row': order.get('order_row'),
        })
        bot.answer_callback_query(
            call.id,
            f"✅ Повторно отмечена: ТТН №{order['ttn_number']} "
            f"(стр. {order.get('order_row', '?')})")
        from master_menu import render_order_card
        render_order_card(order_id, user_id, call.message.message_id)
        return
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        master_edit_state[user_id] = {'action': 'waiting_batch_number',
                                      'order_id': order_id}
        bot.answer_callback_query(call.id)
        bot.send_message(user_id,
                         "📦 *Начало новой пачки*\n\n"
                         "Введите номер накладной, которая лежит *сверху пачки* "
                         "(наибольший номер, с которого вы начинаете печать).\n\n"
                         "Например: `0217975`\n\n"
                         "ℹ️ *Логика заполнения:*\n"
                         "• Эта заявка → ТТН №`0217975` → строка *25* реестра\n"
                         "• Следующая → ТТН №`0217974` → строка 24\n"
                         "• Последняя, 25-я → ТТН №`0217951` → строка 1\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')
        return
    if int(batch['counter']) >= orders_db.BATCH_SIZE:
        bot.answer_callback_query(call.id, "📦 Пачка заполнена, закрываю...")
        _finish_batch(user_id, batch['id'])
        return
    offset = batch['counter']
    order_row = orders_db.BATCH_SIZE - offset
    ttn = orders_db.compute_ttn_number(batch['start_number'], -offset)
    new_counter = orders_db.increment_batch_counter(batch['id'])
    orders_db.set_order_ttn(order_id, ttn, batch['id'], order_row)
    orders_db.set_order_status(order_id, 'printed')
    orders_db.log_order_event(order_id, user_id, 'printed', {
        'ttn_number': ttn, 'order_row': order_row, 'batch_id': batch['id'],
    })

    driver_id = order.get('driver_id')
    if driver_id:
        try:
            msg = (f"✅ Ваша заявка №{order_id} (от {order['date']}, "
                   f"путевой {order['waybill_number']}) распечатана мастером.")
            bot.send_message(int(driver_id), msg)
        except Exception as e:
            logger.exception(f"⚠️ Не удалось отправить уведомление водителю: {e}")

    bot.answer_callback_query(call.id,
                              f"✅ Заявка №{order_id} — ТТН №{ttn} (стр. {order_row})")
    if new_counter >= orders_db.BATCH_SIZE:
        _finish_batch(user_id, batch['id'])
    else:
        from master_menu import master_orders
        master_orders(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith('unprint_order_'))
def unprint_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('unprint_order_', ''))
    order = orders_db.get_order(order_id)
    if not order or not orders_db.can_access_order(order, user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.");
        return
    orders_db.set_order_status(order_id, 'new')
    orders_db.log_order_event(order_id, user_id, 'unprinted', {
        'ttn_number': order.get('ttn_number'),
        'order_row': order.get('order_row'),
    })
    bot.answer_callback_query(call.id,
                              f"↩️ Заявка №{order_id} возвращена в работу. "
                              f"ТТН №{order.get('ttn_number', '—')} сохранён за ней.")
    from master_menu import render_order_card
    render_order_card(order_id, user_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('unreg_order_'))
def unreg_order(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('unreg_order_', ''))
    order = orders_db.get_order(order_id)
    if not order or not orders_db.can_access_order(order, user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.");
        return
    if not order.get('ttn_number'):
        bot.answer_callback_query(call.id, "⚠️ Заявка не в реестре.");
        return
    old = order['ttn_number']
    orders_db.unassign_order_from_batch(order_id)
    orders_db.log_order_event(order_id, user_id, 'unregistered', {
        'old_ttn_number': old,
    })
    bot.answer_callback_query(call.id, f"🗑 Убрана из реестра (был ТТН №{old})")
    from master_menu import render_order_card
    render_order_card(order_id, user_id, call.message.message_id)


# =============================================================
# ТЕКУЩАЯ ПАЧКА (И РУЧНОЙ ВВОД)
# =============================================================
def render_current_registry(user_id, message_id=None):
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton(
            "📝 Начать пачку с ручной накладной",
            callback_data="master_registry_start_manual"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))
        text = ("📦 *Текущая пачка*\n\n"
                "_Пачка ещё не открыта._\n\n"
                "Можно начать пачку с ручной накладной: она займёт строку 25, "
                "а её номер станет номером сверху пачки. Следующие "
                "распечатанные заявки пойдут со строки 24.")
        if message_id:
            safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                                   parse_mode='Markdown', reply_markup=m)
        else:
            bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)
        return

    orders = orders_db.get_batch_orders(batch['id'])
    manual = orders_db.get_manual_registry(user_id, batch['id'])

    text = (f"📦 *Текущая пачка №{batch['id']}*\n\n"
            f"Номер сверху: `{batch['start_number']}`\n"
            f"Заполнено: *{len(orders) + len(manual)}* / {orders_db.BATCH_SIZE}\n"
            f"Открыта: {batch['started_at']}\n\n")

    if orders:
        text += "📄 Заявки из базы:\n"
        for o in orders:
            text += (f"• стр. {o.get('order_row')}: ТТН №`{o.get('ttn_number')}` • "
                     f"{o.get('date')} • {o.get('driver_name')}\n")

    if manual:
        text += "\n📝 Добавленные вручную:\n"
        for me in manual:
            row_info = f"стр. {me['target_row']}" if me.get('target_row') else "свободная"
            text += f"• {row_info} • {me['date']} • ТТН №{me['ttn_number']} • {me['driver_name']}\n"

    if not orders and not manual:
        text += "_Заявок пока нет._\n"

    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📄 Скачать реестр (Word + PDF)",
                                     callback_data="master_registry_download"))
    m.add(types.InlineKeyboardButton("➕ Добавить накладную вручную",
                                     callback_data="master_registry_add_manual"))
    m.add(types.InlineKeyboardButton("✏️ Изменить номер сверху",
                                     callback_data="master_registry_edit_start"))
    m.add(types.InlineKeyboardButton("🗑 Управление записями",
                                     callback_data="master_registry_manage"))
    m.add(types.InlineKeyboardButton("🔄 Сбросить пачку",
                                     callback_data="master_registry_reset"))
    m.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="master_registry"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_back"))
    if message_id:
        safe_edit_message_text(chat_id=user_id, message_id=message_id, text=text,
                               parse_mode='Markdown', reply_markup=m)
    else:
        bot.send_message(user_id, text, parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry')
def show_current_registry(call):
    render_current_registry(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_start_manual')
def master_registry_start_manual(call):
    user_id = call.message.chat.id
    if orders_db.get_active_batch(user_id):
        bot.answer_callback_query(call.id, "Пачка уже открыта.")
        render_current_registry(user_id, call.message.message_id)
        return
    master_edit_state[user_id] = {
        'action': 'manual_reg', 'step': 'ttn', 'start_batch': True,
    }
    bot.answer_callback_query(call.id)
    bot.send_message(
        user_id,
        "📝 *Пачка с ручной накладной*\n\n"
        "Шаг 1 из 5. Введите *номер накладной*, которая лежит сверху пачки.\n"
        "Она займёт строку 25, а её номер станет номером сверху пачки.\n\n"
        "Например: `0217975`\n\n_Отмена: /cancel_",
        parse_mode='Markdown')


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_download')
def master_registry_download(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.");
        return
    orders = orders_db.get_batch_orders(batch['id'])
    manual = orders_db.get_manual_registry(user_id, batch['id'])

    if not orders and not manual:
        bot.answer_callback_query(call.id, "Пачка пуста. Нечего скачивать.");
        return

    output_name = f"Реестр_ТТН_batch{batch['id']}_частичный"
    try:
        docx_path, pdf_path = registry_filler.generate_registry(
            orders, REGISTRY_MASTER_NAME, output_name, manual)
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}");
        return
    bot.answer_callback_query(call.id, "⏳ Отправляю...")
    try:
        with open(docx_path, 'rb') as f:
            bot.send_document(user_id, f,
                              caption=f"📄 Реестр ТТН (Word) — пачка №{batch['id']}")
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                bot.send_document(user_id, f,
                                  caption=f"📄 Реестр ТТН (PDF) — пачка №{batch['id']}")
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Не отправить файл: {e}")

    # Частичное скачивание не должно удалять ручные накладные из пачки.
    render_current_registry(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_add_manual')
def master_registry_add_manual(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.")
        return
    master_edit_state[user_id] = {
        'action': 'manual_reg', 'step': 'ttn', 'batch_id': batch['id'],
    }
    bot.answer_callback_query(call.id)
    bot.send_message(user_id,
                     "📝 *Добавление накладной вручную*\n\n"
                     "Шаг 1 из 5. Введите *номер ТТН* (например, `0217975`):\n\n"
                     "_Отмена: /cancel_", parse_mode='Markdown')


@bot.message_handler(func=lambda m: master_edit_state.get(m.chat.id, {}).get('action') == 'manual_reg')
def handle_manual_reg(message):
    user_id = message.chat.id
    st = master_edit_state.get(user_id)
    if not st: return
    text = (message.text or '').strip()

    if text.lower() in ('/cancel', 'отмена'):
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        render_current_registry(user_id)
        return

    step = st['step']
    if step == 'ttn':
        ttn_text = text.strip()
        if st.get('start_batch'):
            if orders_db.get_active_batch(user_id):
                master_edit_state.pop(user_id, None)
                bot.send_message(user_id,
                                 "⚠️ Появилась активная пачка. "
                                 "Ручная накладная не добавлена.")
                render_current_registry(user_id)
                return
            if not ttn_text.isdigit():
                bot.send_message(user_id, "❌ ТТН должен быть числом. Введите снова:")
                return
            st['start_number'] = ttn_text
            st['ttn_number'] = ttn_text
            st['target_row'] = orders_db.BATCH_SIZE
            st['step'] = 'date'
            bot.send_message(user_id, "Шаг 2 из 5. Введите *дату* (ДД.ММ.ГГ, например 20.10.26):\n\n_Отмена: /cancel_",
                             parse_mode='Markdown')
            return
        batch = orders_db.get_active_batch(user_id)
        target_row = None
        if batch:
            try:
                start_val = int(batch['start_number'])
                ttn_val = int(ttn_text)
                offset = start_val - ttn_val
                calc_row = orders_db.BATCH_SIZE - offset
                if 1 <= calc_row <= orders_db.BATCH_SIZE:
                    target_row = calc_row
                else:
                    bot.send_message(user_id,
                                     f"⚠️ ТТН {ttn_text} вне диапазона текущей пачки (от {start_val - 24} до {start_val}). Введите другой номер или /cancel:")
                    return
            except ValueError:
                bot.send_message(user_id, "❌ ТТН должен быть числом. Введите снова:")
                return

        if not batch:
            bot.send_message(user_id, "⚠️ Нет активной пачки. Начните печать заново.")
            master_edit_state.pop(user_id, None)
            return
        st['batch_id'] = batch['id']
        st['ttn_number'] = ttn_text
        st['target_row'] = target_row
        st['step'] = 'date'
        bot.send_message(user_id, "Шаг 2 из 5. Введите *дату* (ДД.ММ.ГГ, например 20.10.26):\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')
    elif step == 'date':
        try:
            datetime.strptime(text, "%d.%m.%y")
        except ValueError:
            bot.send_message(user_id, "❌ Неверный формат. Введите ДД.ММ.ГГ:");
            return
        st['date'] = text
        st['step'] = 'object'
        bot.send_message(user_id, "Шаг 3 из 5. Введите *наименование объекта*:\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')
    elif step == 'object':
        st['loading_point'] = text
        st['step'] = 'driver'
        bot.send_message(user_id, "Шаг 4 из 5. Введите *ФИО водителя*:\n\n_Отмена: /cancel_", parse_mode='Markdown')
    elif step == 'driver':
        st['driver_name'] = text
        st['step'] = 'car'
        bot.send_message(user_id, "Шаг 5 из 5. Введите *номер машины* (например, А000АА-0):\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')
    elif step == 'car':
        st['car_plate'] = text
        if st.get('start_batch'):
            if orders_db.get_active_batch(user_id):
                master_edit_state.pop(user_id, None)
                bot.send_message(user_id,
                                 "⚠️ Появилась активная пачка. "
                                 "Ручная накладная не добавлена.")
                render_current_registry(user_id)
                return
            entry = {
                'ttn_number': st['ttn_number'],
                'date': st['date'],
                'loading_point': st['loading_point'],
                'driver_name': st['driver_name'],
                'car_plate': st['car_plate'],
                'target_row': orders_db.BATCH_SIZE,
            }
            try:
                orders_db.create_batch_with_manual(
                    user_id, st['start_number'], entry)
            except Exception as e:
                logger.exception(
                    f"❌ Не удалось открыть пачку с ручной накладной: {e}")
                master_edit_state.pop(user_id, None)
                bot.send_message(
                    user_id,
                    f"❌ Не удалось открыть пачку: {e}\n"
                    "Данные не сохранены. Попробуйте снова.")
                render_current_registry(user_id)
                return
            master_edit_state.pop(user_id, None)
            bot.send_message(
                user_id,
                f"✅ Пачка открыта с ручной накладной.\n\n"
                f"📄 ТТН №`{st['ttn_number']}` — строка 25\n"
                f"Следующая печать начнётся со строки 24.",
                parse_mode='Markdown')
            render_current_registry(user_id)
            return
        batch_id = st.get('batch_id')
        batch = orders_db.get_active_batch(user_id)
        if not batch or (batch_id and int(batch['id']) != int(batch_id)):
            bot.send_message(user_id, "⚠️ Пачка уже закрыта или изменилась. "
                                      "Накладная не добавлена.")
            master_edit_state.pop(user_id, None)
            render_current_registry(user_id)
            return
        orders_db.add_manual_registry(user_id, batch['id'], {
            'ttn_number': st['ttn_number'],
            'date': st['date'],
            'loading_point': st['loading_point'],
            'driver_name': st['driver_name'],
            'car_plate': st['car_plate'],
            'target_row': st.get('target_row'),
        })
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "✅ Накладная добавлена в реестр.")
        render_current_registry(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_edit_start')
def master_registry_edit_start(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.");
        return
    master_edit_state[user_id] = {'action': 'edit_batch_start'}
    bot.answer_callback_query(call.id)
    bot.send_message(user_id,
                     f"✏️ *Изменение номера сверху пачки*\n\n"
                     f"Текущий номер: `{batch['start_number']}`\n\n"
                     f"Введите новый номер сверху пачки (наибольший).\n"
                     f"Все ТТН и строки реестра будут пересчитаны.\n\n"
                     f"Например: `0218600`\n\n_Отмена: /cancel_",
                     parse_mode='Markdown')


@bot.message_handler(func=lambda m:
master_edit_state.get(m.chat.id, {}).get('action') == 'edit_batch_start')
def handle_edit_batch_start(message):
    user_id = message.chat.id
    st = master_edit_state.get(user_id)
    if not st: return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.")
        show_master_menu(user_id);
        return
    if not text:
        bot.send_message(user_id, "❌ Введите номер (или /cancel):");
        return
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "Нет активной пачки.");
        return
    orders_db.recalc_batch_ttn(batch['id'], text)
    master_edit_state.pop(user_id, None)
    bot.send_message(user_id,
                     f"✅ Номер сверху обновлён: `{text}`.\nТТН и строки реестра пересчитаны.",
                     parse_mode='Markdown')
    render_current_registry(user_id)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_manage')
def master_registry_manage(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.");
        return
    orders = orders_db.get_batch_orders(batch['id'])
    manual = orders_db.get_manual_registry(user_id, batch['id'])

    if not orders and not manual:
        bot.answer_callback_query(call.id, "В пачке нет заявок.");
        return

    m = types.InlineKeyboardMarkup(row_width=1)
    for o in orders:
        m.add(types.InlineKeyboardButton(
            f"🗑 стр.{o.get('order_row')} • ТТН №{o.get('ttn_number')} • {o.get('driver_name')}",
            callback_data=f"unreg_from_registry_{o['id']}"))

    for me in manual:
        m.add(types.InlineKeyboardButton(
            f"🗑 Ручная • {me['ttn_number']} • {me['driver_name']}",
            callback_data=f"del_manual_reg_{me['id']}"))

    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="master_registry"))
    bot.answer_callback_query(call.id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="Выберите заявку, чтобы убрать её из реестра:",
                           reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('del_manual_reg_'))
def del_manual_reg(call):
    user_id = call.message.chat.id
    entry_id = int(call.data.replace('del_manual_reg_', ''))
    if orders_db.delete_manual_registry(entry_id, user_id):
        bot.answer_callback_query(call.id, "🗑 Ручная накладная удалена.")
    else:
        bot.answer_callback_query(call.id, "Запись не найдена.")
    master_registry_manage(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith('unreg_from_registry_'))
def unreg_from_registry(call):
    user_id = call.message.chat.id
    order_id = int(call.data.replace('unreg_from_registry_', ''))
    order = orders_db.get_order(order_id)
    if not order or not orders_db.can_access_order(order, user_id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа.");
        return
    old = order.get('ttn_number') or '?'
    orders_db.unassign_order_from_batch(order_id)
    orders_db.log_order_event(order_id, user_id, 'unregistered', {
        'old_ttn_number': old, 'source': 'registry_manage',
    })
    bot.answer_callback_query(call.id, f"🗑 Заявка убрана (был ТТН №{old})")
    master_registry_manage(call)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_reset')
def master_registry_reset(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.");
        return
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Да, сбросить",
                                     callback_data="master_registry_reset_confirm"),
          types.InlineKeyboardButton("⬅️ Нет", callback_data="master_registry"))
    bot.answer_callback_query(call.id)
    safe_edit_message_text(chat_id=user_id, message_id=call.message.message_id,
                           text="⚠️ *Сбросить пачку?*\n\nВсе заявки вернутся в «новые», "
                                "счётчик обнулится, ТТН будут присвоены заново при следующей печати.",
                           parse_mode='Markdown', reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'master_registry_reset_confirm')
def master_registry_reset_confirm(call):
    user_id = call.message.chat.id
    batch = orders_db.get_active_batch(user_id)
    if not batch:
        bot.answer_callback_query(call.id, "Нет активной пачки.");
        return
    orders_db.reset_batch(batch['id'])
    orders_db.clear_manual_registry(user_id, batch['id'])
    orders_db.log_order_event(None, user_id, 'batch_reset', {'batch_id': batch['id']})
    bot.answer_callback_query(call.id, "✅ Пачка сброшена.")
    render_current_registry(user_id, call.message.message_id)


# =============================================================
# ЗАВЕРШЕНИЕ ПАЧКИ
# =============================================================
def _finish_batch(master_id, batch_id):
    batch = orders_db.get_batch(batch_id)
    if not batch:
        return
    orders = orders_db.get_batch_orders(batch_id)
    manual = orders_db.get_manual_registry(master_id, batch_id)

    output_name = f"Реестр_ТТН_batch{batch_id}"
    try:
        docx_path, pdf_path = registry_filler.generate_registry(
            orders, REGISTRY_MASTER_NAME, output_name, manual)
    except Exception as e:
        logger.exception(f"❌ Ошибка генерации реестра: {e}")
        bot.send_message(master_id, f"❌ Ошибка генерации реестра: {e}")
        return

    # Закрываем пачку только после успешной генерации реестра.
    orders_db.close_batch(batch_id)
    orders_db.log_order_event(None, master_id, 'batch_closed', {
        'batch_id': batch_id,
        'orders_count': len(orders),
        'manual_count': len(manual),
    })

    if orders:
        lowest = orders[0].get('ttn_number', '?')
        highest = orders[-1].get('ttn_number', '?')
        ttns_line = f"\n📄 ТТН в пачке: от `{lowest}` (стр. 1) до `{highest}` (стр. 25)"
    else:
        ttns_line = ""

    bot.send_message(int(master_id),
                     f"✅ *Пачка закрыта!*\n\n📦 Пачка №{batch_id} — {len(orders) + len(manual)} заявок{ttns_line}",
                     parse_mode='Markdown')

    if os.path.exists(docx_path):
        with open(docx_path, 'rb') as f:
            bot.send_document(int(master_id), f,
                              caption=f"📄 Реестр ТТН (Word) — пачка №{batch_id}")
    if pdf_path and os.path.exists(pdf_path):
        try:
            with open(pdf_path, 'rb') as f:
                bot.send_document(int(master_id), f,
                                  caption=f"📄 Реестр ТТН (PDF) — пачка №{batch_id}")
        except Exception as e:
            logger.exception(f"⚠️ Не отправить PDF: {e}")

    # Ручные накладные остаются в БД как история закрытой пачки.
    master_edit_state[int(master_id)] = {'action': 'waiting_batch_number_after_finish'}
    bot.send_message(int(master_id),
                     "📦 *Новая пачка*\n\nВведите номер накладной *сверху следующей пачки* "
                     "(наибольший номер, с которого начнёте печать).\n\n"
                     "Например: `0218001`\n\n_Отмена: /cancel_",
                     parse_mode='Markdown')


@bot.message_handler(func=lambda m: master_edit_state.get(m.chat.id, {}).get('action') in
                                    ('waiting_batch_number', 'waiting_batch_number_after_finish'))
def handle_batch_number_input(message):
    user_id = message.chat.id
    st = master_edit_state.get(user_id)
    if not st: return
    text = (message.text or '').strip()
    if text.lower() in ('/cancel', 'отмена'):
        master_edit_state.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено.");
        return
    if not text:
        bot.send_message(user_id, "❌ Введите номер (или /cancel):");
        return
    action = st['action']
    master_edit_state.pop(user_id, None)
    batch_id = orders_db.create_batch(user_id, text)
    batch = orders_db.get_batch(batch_id)
    orders_db.log_order_event(None, user_id, 'batch_created', {
        'batch_id': batch_id, 'start_number': text,
    })
    if action == 'waiting_batch_number_after_finish':
        bot.send_message(user_id,
                         f"✅ Новая пачка открыта.\n📦 Номер сверху: `{text}`\n"
                         f"_Следующая печать присвоит ТТН №`{text}` (строка 25)._",
                         parse_mode='Markdown')
        return
    order_id = st.get('order_id')
    if not order_id:
        bot.send_message(user_id, "⚠️ Не найден заказ. Начните печать снова.");
        return
    order = orders_db.get_order(order_id)
    if not order:
        bot.send_message(user_id, "⚠️ Заказ не найден.");
        return
    offset = batch['counter']
    order_row = orders_db.BATCH_SIZE - offset
    ttn = orders_db.compute_ttn_number(batch['start_number'], -offset)
    new_counter = orders_db.increment_batch_counter(batch_id)
    orders_db.set_order_ttn(order_id, ttn, batch_id, order_row)
    orders_db.set_order_status(order_id, 'printed')

    driver_id = order.get('driver_id')
    if driver_id:
        try:
            msg = (f"✅ Ваша заявка №{order_id} (от {order['date']}, "
                   f"путевой {order['waybill_number']}) распечатана мастером.")
            bot.send_message(int(driver_id), msg)
        except Exception as e:
            logger.exception(f"⚠️ Не удалось отправить уведомление водителю: {e}")

    bot.send_message(user_id,
                     f"✅ Заявка №{order_id} помечена как распечатанная.\n"
                     f"📄 ТТН №`{ttn}` (строка {order_row} реестра)\n"
                     f"📦 В пачке осталось: {orders_db.BATCH_SIZE - new_counter}",
                     parse_mode='Markdown')
    if new_counter >= orders_db.BATCH_SIZE:
        _finish_batch(user_id, batch_id)
    else:
        show_master_menu(user_id)
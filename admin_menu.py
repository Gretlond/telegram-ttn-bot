# =============================================================
# АДМИН-МЕНЮ: УПРАВЛЕНИЕ СПРАВОЧНИКАМИ
# =============================================================
from telebot import types
import database
import orders_db
from audit_format import format_events
from config import pending_platform_cargos


def register(bot, masters_dict, save_masters_fn, admin_id):
    admin_id = int(admin_id)
    state = {}

    def is_admin(uid):
        try:
            return int(uid) == admin_id
        except (TypeError, ValueError):
            return False

    def check(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Только администратор.")
            return False
        return True

    SIMPLE_SECTIONS = {
        'drv': {'title': 'Водители', 'store': database.DRIVERS, 'prefix': 'drv'},
        'car': {'title': 'Машины', 'store': database.CARS, 'prefix': 'car'},
        'tr': {'title': 'Прицепы', 'store': database.TRAILERS, 'prefix': 'tr'},
        'loc': {'title': 'Объекты', 'store': database.LOCATIONS, 'prefix': 'loc'},
        'comp': {'title': 'Предприятия', 'store': database.COMPANIES, 'prefix': 'comp'},
        'pcat': {'title': 'Категории площадок', 'store': database.PLATFORM_CATEGORIES, 'prefix': 'pcat'},
        'plat': {'title': 'Грузы площадок', 'store': database.PLATFORM_CARGOS, 'prefix': 'plat'},
    }

    def comp_name(comp_id):
        c = database.COMPANIES.get(comp_id)
        return c['name'] if c else "—"

    def car_type_name(t):
        return "Самосвал" if t == "tipper" else "Площадка (Трал)"

    def plat_cat_name(cat_id):
        c = database.PLATFORM_CATEGORIES.get(cat_id)
        return f"{c.get('icon', '📦')} {c.get('name', '—')}" if c else "—"

    TTN_HEADER_UI = (
        ("shipper", "Грузоотправитель", "наименование и адрес"),
        ("shipper_unp", "УНП грузоотправителя", "УНП"),
        ("consignee", "Грузополучатель", "наименование и адрес"),
        ("consignee_unp", "УНП грузополучателя", "УНП"),
        ("customer", "Заказчик автомобильной перевозки", "наименование и адрес"),
        ("customer_unp", "УНП заказчика", "УНП"),
    )

    def ttn_header_ui(field):
        for key, label, hint in TTN_HEADER_UI:
            if key == field:
                return label, hint
        return None, None

    def show_ttn_header(uid, msg_id=None):
        lines = [
            "📋 Постоянные реквизиты ТТН",
            "",
            "Эти данные сохраняются и подставляются во все новые ТТН.",
            "Чтобы изменить значение, нажмите кнопку ниже.",
            "",
        ]
        m = types.InlineKeyboardMarkup(row_width=1)
        for key, label, hint in TTN_HEADER_UI:
            value = str(database.TTN_HEADER.get(key) or "").strip() or "—"
            lines.append(f"{label}: {value}")
            m.add(types.InlineKeyboardButton(
                f"✏️ {label}", callback_data=f"adm_ttn_edit|{key}"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_menu"))
        text = "\n".join(lines)
        if msg_id:
            try:
                bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                      reply_markup=m)
                return
            except Exception:
                pass
        bot.send_message(uid, text, reply_markup=m)

    def item_title(t, item_id, item):
        if t == 'drv':
            car = database.CARS.get(item.get('car_id', ''))
            car_txt = f" — {car['model']} ({car['plate']})" if car else " — без машины"
            return f"{item.get('name', '?')}{car_txt} • {comp_name(item.get('company_id', ''))}"
        if t == 'car':
            ctype = "🚛" if item.get('type') == 'tipper' else "🚜"
            return f"{ctype} {item.get('model', '?')} ({item.get('plate', '?')}) • {item.get('capacity', '?')} т"
        if t == 'tr':
            return database.trailer_number(item)
        if t == 'loc':
            return f"{item.get('name', '?')} — {item.get('master', '?')}"
        if t == 'comp':
            drivers = database.get_drivers_by_company(item_id)
            return f"{item.get('name', '?')} ({len(drivers)} вод.)"
        if t == 'ct':
            subs = item.get('subcategories') or {}
            dist = " 📏" if item.get('has_distance') else ""
            return f"{item.get('name', '?')}{dist} ({len(subs)} подк.)"
        if t == 'cd':
            return str(item)
        if t == 'un':
            return str(item)
        if t == 'pcat':
            return f"{item.get('icon', '📦')} {item.get('name', '?')}"
        if t == 'plat':
            return f"{plat_cat_name(item.get('category'))} • {item.get('name', '?')}"
        return item_id

    def main_markup():
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton("👤 Водители", callback_data="adm_list_drv"),
            types.InlineKeyboardButton("🚛 Машины", callback_data="adm_list_car"),
            types.InlineKeyboardButton("🚚 Прицепы", callback_data="adm_list_tr"),
            types.InlineKeyboardButton("📍 Объекты", callback_data="adm_list_loc"),
            types.InlineKeyboardButton("🏢 Предприятия", callback_data="adm_list_comp"),
        )
        m.add(
            types.InlineKeyboardButton("📦 Материалы", callback_data="adm_list_ct"),
            types.InlineKeyboardButton("📏 Расстояния", callback_data="adm_list_cd"),
            types.InlineKeyboardButton("📐 Единицы", callback_data="adm_list_un"),
        )
        m.add(
            types.InlineKeyboardButton("🚜 Грузы площадок", callback_data="adm_list_plat"),
        )
        m.add(types.InlineKeyboardButton("📋 Реквизиты ТТН", callback_data="adm_ttn_header"))
        m.add(types.InlineKeyboardButton("🕘 Аудит заявок", callback_data="adm_audit"))
        m.add(types.InlineKeyboardButton("⬅️ В кабинет", callback_data="master_back"))
        return m

    def show_main(uid, msg_id=None):
        text = ("⚙️ *Управление справочниками*\n\nВыберите раздел.\n\n"
                "_Все изменения сохраняются сразу._")
        if msg_id:
            try:
                bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                      parse_mode='Markdown', reply_markup=main_markup())
                return
            except Exception:
                pass
        bot.send_message(uid, text, parse_mode='Markdown', reply_markup=main_markup())

    @bot.callback_query_handler(func=lambda c: c.data == 'adm_menu')
    def cb_adm_menu(call):
        if not check(call): return
        bot.answer_callback_query(call.id)
        show_main(call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data == 'adm_ttn_header')
    def cb_adm_ttn_header(call):
        if not check(call): return
        bot.answer_callback_query(call.id)
        show_ttn_header(call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ttn_edit|'))
    def cb_adm_ttn_edit(call):
        if not check(call): return
        field = call.data.split('|', 1)[1]
        label, hint = ttn_header_ui(field)
        if not label:
            bot.answer_callback_query(call.id, "Ошибка поля."); return
        uid = call.message.chat.id
        state[uid] = {'action': 'ttn_header_edit', 'field': field}
        bot.answer_callback_query(call.id)
        bot.send_message(
            uid,
            f"✏️ {label}\n\nВведите {hint}.\n"
            "Чтобы очистить значение, отправьте «-».\n\n_Отмена: /cancel_",
            parse_mode='Markdown',
        )

    @bot.message_handler(
        func=lambda m: state.get(m.chat.id, {}).get('action') == 'ttn_header_edit')
    def process_ttn_header_edit(message):
        uid = message.chat.id
        st = state.get(uid)
        if not st:
            return
        text = (message.text or '').strip()
        if text.lower() in ('/cancel', 'отмена'):
            state.pop(uid, None)
            bot.send_message(uid, "❌ Отменено.")
            show_main(uid)
            return
        field = st.get('field')
        label, _ = ttn_header_ui(field)
        if not label:
            state.pop(uid, None)
            bot.send_message(uid, "❌ Поле не найдено.")
            show_main(uid)
            return
        value = "" if text == '-' else text
        if field.endswith('_unp'):
            value = value.replace(' ', '')
        if not value and text != '-':
            bot.send_message(uid, "❌ Значение не может быть пустым. Отправьте «-», чтобы очистить.")
            return
        database.update_ttn_header(**{field: value})
        state.pop(uid, None)
        bot.send_message(uid, f"✅ Сохранено: {label}")
        show_ttn_header(uid)

    # =========================================================
    # АУДИТ И УДАЛЁННЫЕ ЗАЯВКИ
    # =========================================================
    @bot.callback_query_handler(func=lambda c: c.data == 'adm_audit')
    def cb_audit(call):
        if not check(call): return
        events = orders_db.get_recent_events(30)
        text = "🕘 Журнал действий (последние 30)\n\n"
        text += format_events(events) if events else "Событий пока нет."
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🗑 Удалённые заявки",
                                         callback_data="adm_deleted"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_menu"))
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=text, reply_markup=m)
        except Exception:
            bot.send_message(call.message.chat.id, text, reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data == 'adm_deleted')
    def cb_deleted(call):
        if not check(call): return
        deleted = orders_db.get_deleted_orders(30)
        text = "🗑 Удалённые заявки (последние 30)\n\n"
        if not deleted:
            text += "Удалённых заявок нет."
        m = types.InlineKeyboardMarkup(row_width=1)
        for order in deleted:
            text += (f"№{order['id']} • мастер {order.get('master_id', '—')} • "
                     f"{order.get('date', '—')} • удалена {order.get('deleted_at', '—')}\n")
            m.add(types.InlineKeyboardButton(
                f"♻️ Восстановить №{order['id']}",
                callback_data=f"adm_restore|{order['id']}"))
        m.add(types.InlineKeyboardButton("⬅️ К журналу", callback_data="adm_audit"))
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=text, reply_markup=m)
        except Exception:
            bot.send_message(call.message.chat.id, text, reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_restore|'))
    def cb_restore(call):
        if not check(call): return
        try:
            order_id = int(call.data.split('|', 1)[1])
        except (IndexError, ValueError):
            bot.answer_callback_query(call.id, "Ошибка номера заявки.")
            return
        if orders_db.restore_order(order_id, call.from_user.id):
            bot.answer_callback_query(call.id, f"♻️ Заявка №{order_id} восстановлена.")
        else:
            bot.answer_callback_query(call.id, "Заявка не найдена или не удалена.")
        cb_deleted(call)

    # =========================================================
    # СПИСКИ
    # =========================================================
    def render_list(t, uid, msg_id=None):
        if t == 'plat':
            # Особый случай: для площадок показываем категории
            text = "🚜 *Грузы площадок*\n\nВыберите категорию для просмотра или добавления:"
            m = types.InlineKeyboardMarkup(row_width=1)
            for cat_id, cat in database.PLATFORM_CATEGORIES.items():
                cnt = len([c for c in database.PLATFORM_CARGOS.values() if c.get('category') == cat_id])
                m.add(types.InlineKeyboardButton(
                    f"{cat.get('icon', '📦')} {cat.get('name', '?')} ({cnt})",
                    callback_data=f"adm_cat_view|{cat_id}"
                ))
            m.add(types.InlineKeyboardButton("➕ Добавить категорию", callback_data="adm_add|pcat"))
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_menu"))
            if msg_id:
                try:
                    bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                          parse_mode='Markdown', reply_markup=m)
                    return
                except Exception:
                    pass
            bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)
            return

        if t in SIMPLE_SECTIONS:
            info = SIMPLE_SECTIONS[t]
        else:
            info = {'ct': {'title': 'Материалы', 'store': database.CARGO_TYPES, 'prefix': 'ct'},
                    'cd': {'title': 'Расстояния', 'store': database.CARGO_DISTANCES, 'prefix': 'cd'},
                    'un': {'title': 'Единицы', 'store': database.UNITS, 'prefix': 'un'}}[t]

        store = info['store']
        title = info['title']

        text = f"*{title}* ({len(store)}):\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        if not store:
            text += "_Список пуст._\n"
        else:
            for item_id, item in store.items():
                text += f"• {item_title(t, item_id, item)}\n"
                m.add(types.InlineKeyboardButton(
                    item_title(t, item_id, item),
                    callback_data=f"adm_show|{t}|{item_id}"
                ))
        m.add(types.InlineKeyboardButton("➕ Добавить", callback_data=f"adm_add|{t}"))
        m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="adm_menu"))

        if msg_id:
            try:
                bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                      parse_mode='Markdown', reply_markup=m)
                return
            except Exception:
                pass
        bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_list_'))
    def cb_adm_list(call):
        if not check(call): return
        t = call.data.replace('adm_list_', '')
        bot.answer_callback_query(call.id)
        render_list(t, call.message.chat.id, call.message.message_id)

    # =========================================================
    # СПИСОК ГРУЗОВ ВНУТРИ КАТЕГОРИИ
    # =========================================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_cat_view|'))
    def cb_adm_cat_view(call):
        if not check(call): return
        cat_id = call.data.split('|', 1)[1]
        cat = database.PLATFORM_CATEGORIES.get(cat_id)
        if not cat:
            bot.answer_callback_query(call.id, "Категория не найдена.")
            return

        bot.answer_callback_query(call.id)
        text = f"{cat.get('icon', '📦')} *{cat.get('name', '')}*\n\nСписок грузов:\n\n"
        cargos = {k: v for k, v in database.PLATFORM_CARGOS.items() if v.get('category') == cat_id}
        m = types.InlineKeyboardMarkup(row_width=1)

        if not cargos:
            text += "_Пусто_"
        else:
            for cid, c in cargos.items():
                m.add(types.InlineKeyboardButton(c['name'], callback_data=f"adm_show|plat|{cid}"))

        m.add(types.InlineKeyboardButton("➕ Добавить груз сюда", callback_data=f"adm_add_plat|{cat_id}"))
        m.add(types.InlineKeyboardButton("⚙️ Настройки категории", callback_data=f"adm_show|pcat|{cat_id}"))
        m.add(types.InlineKeyboardButton("⬅️ К категориям", callback_data="adm_list_plat"))

        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=text, parse_mode='Markdown', reply_markup=m)
        except Exception:
            pass

    # =========================================================
    # КАРТОЧКА ЭЛЕМЕНТА
    # =========================================================
    def render_item(t, item_id, uid, msg_id=None):
        info = SIMPLE_SECTIONS.get(t)
        if t in SIMPLE_SECTIONS:
            store = info['store']
        elif t == 'ct':
            store = database.CARGO_TYPES
        elif t == 'cd':
            store = database.CARGO_DISTANCES
        elif t == 'un':
            store = database.UNITS
        else:
            return

        item = store.get(item_id)
        if item is None and t not in ('cd', 'un'):
            bot.send_message(uid, "Запись не найдена.")
            return

        m = types.InlineKeyboardMarkup(row_width=1)

        if t == 'drv':
            car = database.CARS.get(item.get('car_id', ''))
            car_txt = f"{car['model']} ({car['plate']})" if car else "—"
            text = (f"👤 *Водитель*\n\nФИО: {item.get('name', '—')}\n"
                    f"Машина: {car_txt}\nПредприятие: {comp_name(item.get('company_id', ''))}")
            m.add(types.InlineKeyboardButton("✏️ ФИО", callback_data=f"adm_editfld|drv|{item_id}|name"))
            m.add(types.InlineKeyboardButton("🏢 Предприятие", callback_data=f"adm_editfld|drv|{item_id}|company"))
            m.add(types.InlineKeyboardButton("🚛 Машина", callback_data=f"adm_editfld|drv|{item_id}|car"))
        elif t == 'car':
            ctype = car_type_name(item.get('type'))
            text = (f"🚛 *Машина*\n\nМарка: {item.get('model', '—')}\n"
                    f"Госномер: {item.get('plate', '—')}\nГрузоподъёмность: {item.get('capacity', '—')} т\n"
                    f"Тип: {ctype}")
            m.add(types.InlineKeyboardButton("✏️ Марка", callback_data=f"adm_editfld|car|{item_id}|model"))
            m.add(types.InlineKeyboardButton("✏️ Госномер", callback_data=f"adm_editfld|car|{item_id}|plate"))
            m.add(types.InlineKeyboardButton("⚖️ Грузоподъёмность",
                                             callback_data=f"adm_editfld|car|{item_id}|capacity"))
            m.add(types.InlineKeyboardButton("⚙️ Тип машины", callback_data=f"adm_editfld|car|{item_id}|type"))
        elif t == 'tr':
            text = (f"🚚 *Прицеп*\n\nНомер: {database.trailer_number(item)}")
            m.add(types.InlineKeyboardButton("✏️ Номер", callback_data=f"adm_editfld|tr|{item_id}|plate"))
        elif t == 'loc':
            text = (f"📍 *Объект*\n\nНазвание: {item.get('name', '—')}\nМастер: {item.get('master', '—')}")
            m.add(types.InlineKeyboardButton("✏️ Название", callback_data=f"adm_editfld|loc|{item_id}|name"))
            m.add(types.InlineKeyboardButton("✏️ Мастер", callback_data=f"adm_editfld|loc|{item_id}|master"))
        elif t == 'comp':
            drivers = database.get_drivers_by_company(item_id)
            text = (f"🏢 *Предприятие*\n\nНазвание: {item.get('name', '—')}\n"
                    f"Водителей: {len(drivers)}")
            m.add(types.InlineKeyboardButton("✏️ Название", callback_data=f"adm_editfld|comp|{item_id}|name"))
        elif t == 'ct':
            subs = item.get('subcategories') or {}
            dist = "✅ Да" if item.get('has_distance') else "❌ Нет"
            text = (f"📦 *Материал*\n\nНазвание: {item.get('name', '—')}\n"
                    f"Показывать расстояния: {dist}\n"
                    f"Подкатегорий: {len(subs)}\n")
            if subs:
                text += "\n"
                for sid, sname in subs.items():
                    text += f"  • {sname}\n"
            m.add(types.InlineKeyboardButton("✏️ Название", callback_data=f"adm_editfld|ct|{item_id}|name"))
            toggle_label = "⚙️ Расстояния: вкл" if item.get('has_distance') else "⚙️ Расстояния: выкл"
            m.add(types.InlineKeyboardButton(toggle_label, callback_data=f"adm_ct_toggle_dist|{item_id}"))
            m.add(types.InlineKeyboardButton(f"📋 Подкатегории ({len(subs)})",
                                             callback_data=f"adm_ct_subs|{item_id}"))
        elif t == 'cd':
            text = f"📏 *Расстояние*\n\nЗначение: {item}"
            m.add(types.InlineKeyboardButton("✏️ Изменить", callback_data=f"adm_editfld|cd|{item_id}|text"))
        elif t == 'un':
            text = f"📐 *Единица измерения*\n\nОбозначение: {item}"
            m.add(types.InlineKeyboardButton("✏️ Изменить", callback_data=f"adm_editfld|un|{item_id}|name"))
        elif t == 'pcat':
            text = (f"📁 *Настройки категории*\n\n"
                    f"Название: {item.get('name', '—')}\n"
                    f"Иконка: {item.get('icon', '📦')}")
            m.add(types.InlineKeyboardButton("✏️ Название", callback_data=f"adm_editfld|pcat|{item_id}|name"))
            m.add(types.InlineKeyboardButton("🖼 Иконка", callback_data=f"adm_editfld|pcat|{item_id}|icon"))
        elif t == 'plat':
            text = (f"🚜 *Груз площадки*\n\nНазвание: {item.get('name', '—')}\n"
                    f"Категория: {plat_cat_name(item.get('category'))}")
            m.add(types.InlineKeyboardButton("✏️ Название", callback_data=f"adm_editfld|plat|{item_id}|name"))
            m.add(types.InlineKeyboardButton("⚙️ Категория", callback_data=f"adm_editfld|plat|{item_id}|category"))

        m.add(types.InlineKeyboardButton("🗑 Удалить", callback_data=f"adm_del|{t}|{item_id}"))

        # Кнопка "Назад"
        if t == 'pcat':
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_cat_view|{item_id}"))
        elif t == 'plat':
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_cat_view|{item.get('category')}"))
        else:
            m.add(types.InlineKeyboardButton("⬅️ К списку", callback_data=f"adm_list_{t}"))

        if msg_id:
            try:
                bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                      parse_mode='Markdown', reply_markup=m)
                return
            except Exception:
                pass
        bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_show|'))
    def cb_adm_show(call):
        if not check(call): return
        _, t, item_id = call.data.split('|', 2)
        bot.answer_callback_query(call.id)
        render_item(t, item_id, call.message.chat.id, call.message.message_id)

    # =========================================================
    # ДОБАВЛЕНИЕ
    # =========================================================
    ADD_PROMPTS = {
        'drv': ('add_drv_name', "👤 Введите ФИО водителя:"),
        'car': ('add_car_model', "🚛 Введите марку машины:"),
        'tr': ('add_tr_plate', "🚚 Введите номер прицепа:"),
        'loc': ('add_loc_name', "📍 Введите название объекта:"),
        'comp': ('add_comp_name', "🏢 Введите название предприятия:"),
        'ct': ('add_ct_name', "📦 Введите название материала:"),
        'cd': ('add_cd_text', "📏 Введите текст расстояния (например, «на расстояние до 5 км»):"),
        'un': ('add_un_name', "📐 Введите обозначение единицы (например, «тн» или «м³»):"),
        'pcat': ('add_pcat_name', "📁 Введите название категории (например, ЖБИ):"),
    }

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_add|'))
    def cb_adm_add(call):
        if not check(call): return
        t = call.data.split('|', 1)[1]
        if t not in ADD_PROMPTS:
            bot.answer_callback_query(call.id, "Ошибка")
            return
        action, prompt = ADD_PROMPTS[t]
        state[call.message.chat.id] = {'action': action}
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, prompt + "\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_add_plat|'))
    def cb_adm_add_plat(call):
        if not check(call): return
        cat_id = call.data.split('|', 1)[1]
        state[call.message.chat.id] = {'action': 'add_plat_name', 'cat_id': cat_id}
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🚜 Введите название нового груза:\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')

    @bot.message_handler(func=lambda m: state.get(m.chat.id, {}).get('action', '').startswith('add_'))
    def process_add(message):
        uid = message.chat.id
        st = state.get(uid)
        if not st: return
        text = (message.text or '').strip()
        if text.lower() in ('/cancel', 'отмена'):
            state.pop(uid, None)
            bot.send_message(uid, "❌ Отменено.")
            show_main(uid)
            return
        action = st['action']

        if action == 'add_drv_name':
            if len(text) < 3:
                bot.send_message(uid, "❌ Слишком короткое ФИО:");
                return
            st['name'] = text
            st['action'] = 'add_drv_company'
            m = types.InlineKeyboardMarkup(row_width=1)
            for cid, c in database.COMPANIES.items():
                m.add(types.InlineKeyboardButton(c['name'], callback_data=f"adm_newdrv_comp|{cid}"))
            bot.send_message(uid, "🏢 Выберите предприятие:", reply_markup=m)
            return

        if action == 'add_car_model':
            if len(text) < 2:
                bot.send_message(uid, "❌ Введите марку:");
                return
            st['model'] = text
            st['action'] = 'add_car_plate'
            bot.send_message(uid, "🔢 Введите госномер:");
            return
        if action == 'add_car_plate':
            st['plate'] = text
            st['action'] = 'add_car_capacity'
            bot.send_message(uid, "⚖️ Грузоподъёмность (т), например 20.65.\n"
                                  "Можно «-» — по умолчанию 20.0:");
            return
        if action == 'add_car_capacity':
            try:
                cap = 20.0 if text == '-' else float(text.replace(',', '.'))
            except ValueError:
                bot.send_message(uid, "❌ Введите число или «-»:");
                return
            st['capacity'] = cap
            st['action'] = 'add_car_type'
            from keyboards import get_car_type_keyboard
            bot.send_message(uid, "Выберите тип машины:", reply_markup=get_car_type_keyboard())
            return

        if action == 'add_tr_plate':
            if len(text) < 3:
                bot.send_message(uid, "❌ Слишком короткий номер:");
                return
            database.add_trailer(text)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Прицеп добавлен: {text}")
            render_list('tr', uid);
            return

        if action == 'add_loc_name':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком короткое название:");
                return
            st['name'] = text
            st['action'] = 'add_loc_master'
            bot.send_message(uid, "👤 Введите ФИО мастера:");
            return
        if action == 'add_loc_master':
            database.add_location(st['name'], text)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Объект добавлен: {st['name']} — {text}")
            render_list('loc', uid);
            return

        if action == 'add_comp_name':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком короткое название:");
                return
            database.add_company(text)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Предприятие добавлено: {text}")
            render_list('comp', uid);
            return

        if action == 'add_ct_name':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком короткое название:");
                return
            st['name'] = text
            st['action'] = 'add_ct_hasdist'
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("✅ Да", callback_data="adm_ct_new_dist|1"),
                types.InlineKeyboardButton("❌ Нет", callback_data="adm_ct_new_dist|0")
            )
            bot.send_message(uid, f"Материал: {text}\n\nПоказывать выбор расстояния?", reply_markup=m)
            return

        if action == 'add_cd_text':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком коротко:");
                return
            database.add_distance(text)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Расстояние добавлено: {text}")
            render_list('cd', uid);
            return

        if action == 'add_un_name':
            if len(text) < 1:
                bot.send_message(uid, "❌ Слишком коротко:");
                return
            database.add_unit(text)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Единица добавлена: {text}")
            render_list('un', uid);
            return

        if action == 'add_pcat_name':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком короткое название:");
                return
            st['name'] = text
            st['action'] = 'add_pcat_icon'
            bot.send_message(uid, "🖼 Введите иконку для категории (эмодзи, например 🚜):")
            return
        if action == 'add_pcat_icon':
            icon = text if text else "📦"
            database.add_platform_category(st['name'], icon)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Категория добавлена: {icon} {st['name']}")
            render_list('plat', uid);
            return

        if action == 'add_plat_name':
            if len(text) < 2:
                bot.send_message(uid, "❌ Слишком короткое название:");
                return
            cat_id = st.get('cat_id')
            database.add_platform_cargo(text, cat_id)
            state.pop(uid, None)
            bot.send_message(uid, f"✅ Груз добавлен: {text}")

            # Показываем обновленный список внутри категории
            cat = database.PLATFORM_CATEGORIES.get(cat_id, {})
            text_view = f"{cat.get('icon', '📦')} *{cat.get('name', '')}*\n\nСписок грузов:\n\n"
            cargos = {k: v for k, v in database.PLATFORM_CARGOS.items() if v.get('category') == cat_id}
            m = types.InlineKeyboardMarkup(row_width=1)
            for cid, c in cargos.items():
                m.add(types.InlineKeyboardButton(c['name'], callback_data=f"adm_show|plat|{cid}"))
            m.add(types.InlineKeyboardButton("➕ Добавить груз сюда", callback_data=f"adm_add_plat|{cat_id}"))
            m.add(types.InlineKeyboardButton("⚙️ Настройки категории", callback_data=f"adm_show|pcat|{cat_id}"))
            m.add(types.InlineKeyboardButton("⬅️ К категориям", callback_data="adm_list_plat"))
            bot.send_message(uid, text_view, parse_mode='Markdown', reply_markup=m)
            return

    @bot.callback_query_handler(func=lambda c: c.data.startswith('car_type_'))
    def cb_add_car_type(call):
        if not check(call): return
        uid = call.message.chat.id
        st = state.get(uid)
        if not st or st.get('action') != 'add_car_type':
            bot.answer_callback_query(call.id, "Сессия истекла.");
            return
        ctype = 'tipper' if call.data == 'car_type_tipper' else 'platform'
        database.add_car(st['model'], st['plate'], st['capacity'], ctype)
        state.pop(uid, None)
        bot.answer_callback_query(call.id, "✅ Машина добавлена.")
        bot.edit_message_text(chat_id=uid, message_id=call.message.message_id,
                              text=f"✅ Машина добавлена: {st['model']} ({st['plate']})")
        render_list('car', uid)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_plat_new_cat|'))
    def cb_adm_plat_new_cat(call):
        # ЭТОТ ОБРАБОТЧИК БОЛЬШЕ НЕ НУЖЕН, ТАК КАК МЫ ДОБАВЛЯЕМ ГРУЗ В КОНКРЕТНУЮ КАТЕГОРИЮ
        pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_newdrv_comp|'))
    def cb_adm_newdrv_comp(call):
        if not check(call): return
        uid = call.message.chat.id
        st = state.get(uid)
        if not st or st.get('action') != 'add_drv_company':
            bot.answer_callback_query(call.id, "Сессия истекла.");
            return
        comp_id = call.data.split('|', 1)[1]
        st['company_id'] = comp_id
        st['action'] = 'add_drv_car'
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🚫 Без машины", callback_data="adm_newdrv_car|__none__"))
        for cid, c in database.CARS.items():
            m.add(types.InlineKeyboardButton(f"{c['model']} ({c['plate']})",
                                             callback_data=f"adm_newdrv_car|{cid}"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(chat_id=uid, message_id=call.message.message_id,
                              text=f"🏢 {database.COMPANIES[comp_id]['name']}\n\n🚛 Выберите машину:",
                              reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_newdrv_car|'))
    def cb_adm_newdrv_car(call):
        if not check(call): return
        uid = call.message.chat.id
        st = state.get(uid)
        if not st or st.get('action') != 'add_drv_car':
            bot.answer_callback_query(call.id, "Сессия истекла.");
            return
        car_id = call.data.split('|', 1)[1]
        if car_id == '__none__': car_id = ""
        database.add_driver(st['name'], car_id, st['company_id'])
        state.pop(uid, None)
        bot.answer_callback_query(call.id, "✅ Водитель добавлен.")
        bot.send_message(uid, f"✅ Водитель добавлен: {st['name']}")
        render_list('drv', uid)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_new_dist|'))
    def cb_adm_ct_new_dist(call):
        if not check(call): return
        uid = call.message.chat.id
        st = state.get(uid)
        if not st or st.get('action') != 'add_ct_hasdist':
            bot.answer_callback_query(call.id, "Сессия истекла.");
            return
        hd = call.data.split('|', 1)[1] == '1'
        database.add_cargo_type(st['name'], hd)
        state.pop(uid, None)
        bot.answer_callback_query(call.id, "✅ Материал добавлен.")
        bot.send_message(uid, f"✅ Материал добавлен: {st['name']}")
        render_list('ct', uid)

    EDIT_PROMPTS = {
        ('drv', 'name'): "👤 Введите новое ФИО:",
        ('car', 'model'): "🚛 Введите марку:",
        ('car', 'plate'): "🔢 Введите госномер:",
        ('car', 'capacity'): "⚖️ Грузоподъёмность (т), например 20.65:",
        ('tr', 'model'): "🚚 Введите марку:",
        ('tr', 'plate'): "🔢 Введите госномер:",
        ('loc', 'name'): "📍 Введите название объекта:",
        ('loc', 'master'): "👤 Введите ФИО мастера:",
        ('comp', 'name'): "🏢 Введите название предприятия:",
        ('ct', 'name'): "📦 Введите название материала:",
        ('cd', 'text'): "📏 Введите текст расстояния:",
        ('un', 'name'): "📐 Введите обозначение единицы:",
        ('pcat', 'name'): "📁 Введите название категории:",
        ('pcat', 'icon'): "🖼 Введите иконку (эмодзи):",
        ('plat', 'name'): "🚜 Введите название груза:",
    }

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_editfld|'))
    def cb_adm_editfld(call):
        if not check(call): return
        _, t, item_id, field = call.data.split('|', 3)
        uid = call.message.chat.id

        if t == 'drv' and field == 'car':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🚫 Без машины",
                                             callback_data=f"adm_setcar|{item_id}|__none__"))
            for cid, c in database.CARS.items():
                m.add(types.InlineKeyboardButton(f"{c['model']} ({c['plate']})",
                                                 callback_data=f"adm_setcar|{item_id}|{cid}"))
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_show|drv|{item_id}"))
            bot.send_message(uid, "🚛 Выберите машину:", reply_markup=m)
            return

        if t == 'drv' and field == 'company':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(row_width=1)
            for cid, c in database.COMPANIES.items():
                m.add(types.InlineKeyboardButton(c['name'],
                                                 callback_data=f"adm_setcomp|{item_id}|{cid}"))
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_show|drv|{item_id}"))
            bot.send_message(uid, "🏢 Выберите предприятие:", reply_markup=m)
            return

        if t == 'car' and field == 'type':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(types.InlineKeyboardButton("🚛 Самосвал",
                                             callback_data=f"adm_setctype|{item_id}|tipper"),
                  types.InlineKeyboardButton("🚜 Площадка",
                                             callback_data=f"adm_setctype|{item_id}|platform"))
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_show|car|{item_id}"))
            bot.send_message(uid, "Выберите тип:", reply_markup=m)
            return

        if t == 'plat' and field == 'category':
            bot.answer_callback_query(call.id)
            m = types.InlineKeyboardMarkup(row_width=1)
            for cid, c in database.PLATFORM_CATEGORIES.items():
                m.add(types.InlineKeyboardButton(f"{c.get('icon', '📦')} {c.get('name', '')}",
                                                 callback_data=f"adm_setplatcat|{item_id}|{cid}"))
            m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_show|plat|{item_id}"))
            bot.send_message(uid, "Выберите категорию:", reply_markup=m)
            return

        prompt = EDIT_PROMPTS.get((t, field))
        if not prompt:
            bot.answer_callback_query(call.id, "Это поле нельзя изменить.")
            return
        state[uid] = {'action': 'edit_field', 't': t, 'item_id': item_id, 'field': field}
        bot.answer_callback_query(call.id)
        bot.send_message(uid, prompt + "\n\n_Отмена: /cancel_", parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_setctype|'))
    def cb_adm_setctype(call):
        if not check(call): return
        _, car_id, ctype = call.data.split('|', 2)
        database.update_car(car_id, type=ctype)
        bot.answer_callback_query(call.id, "✅ Тип обновлен.")
        render_item('car', car_id, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_setplatcat|'))
    def cb_adm_setplatcat(call):
        if not check(call): return
        _, p_id, cat_id = call.data.split('|', 2)
        database.update_platform_cargo(p_id, category=cat_id)
        bot.answer_callback_query(call.id, "✅ Категория обновлена.")
        render_item('plat', p_id, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_setcar|'))
    def cb_adm_setcar(call):
        if not check(call): return
        _, drv_id, car_id = call.data.split('|', 2)
        if car_id == '__none__': car_id = ""
        database.update_driver(drv_id, car_id=car_id)
        bot.answer_callback_query(call.id, "✅ Машина обновлена.")
        render_item('drv', drv_id, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_setcomp|'))
    def cb_adm_setcomp(call):
        if not check(call): return
        _, drv_id, comp_id = call.data.split('|', 2)
        database.update_driver(drv_id, company_id=comp_id)
        bot.answer_callback_query(call.id, "✅ Предприятие обновлено.")
        render_item('drv', drv_id, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_toggle_dist|'))
    def cb_adm_ct_toggle_dist(call):
        if not check(call): return
        ct_id = call.data.split('|', 1)[1]
        ct = database.CARGO_TYPES.get(ct_id)
        if not ct:
            bot.answer_callback_query(call.id, "Не найдено.");
            return
        new_val = not ct.get('has_distance', False)
        database.update_cargo_type(ct_id, has_distance=new_val)
        bot.answer_callback_query(call.id, "✅ Обновлено.")
        render_item('ct', ct_id, call.message.chat.id, call.message.message_id)

    @bot.message_handler(func=lambda m: state.get(m.chat.id, {}).get('action') == 'edit_field')
    def process_edit_field(message):
        uid = message.chat.id
        st = state.get(uid)
        if not st: return
        text = (message.text or '').strip()
        if text.lower() in ('/cancel', 'отмена'):
            state.pop(uid, None)
            bot.send_message(uid, "❌ Отменено.");
            return
        t = st['t'];
        item_id = st['item_id'];
        field = st['field']

        if t == 'car' and field == 'capacity':
            try:
                value = float(text.replace(',', '.'))
            except ValueError:
                bot.send_message(uid, "❌ Введите число:");
                return
        else:
            if len(text) < 1:
                bot.send_message(uid, "❌ Слишком коротко:");
                return
            value = text

        if t == 'drv':
            database.update_driver(item_id, **{field: value})
        elif t == 'car':
            database.update_car(item_id, **{field: value})
        elif t == 'tr':
            database.update_trailer(item_id, **{field: value})
        elif t == 'loc':
            database.update_location(item_id, **{field: value})
        elif t == 'comp':
            database.update_company(item_id, **{field: value})
        elif t == 'ct':
            database.update_cargo_type(item_id, name=value)
        elif t == 'cd':
            database.update_distance(item_id, value)
        elif t == 'un':
            database.update_unit(item_id, value)
        elif t == 'pcat':
            if field == 'name':
                database.update_platform_category(item_id, name=value)
            elif field == 'icon':
                database.update_platform_category(item_id, icon=value)
        elif t == 'plat':
            database.update_platform_cargo(item_id, name=value)

        state.pop(uid, None)
        bot.send_message(uid, "✅ Обновлено.")
        render_item(t, item_id, uid)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_subs|'))
    def cb_adm_ct_subs(call):
        if not check(call): return
        ct_id = call.data.split('|', 1)[1]
        bot.answer_callback_query(call.id)
        render_subs(ct_id, call.message.chat.id, call.message.message_id)

    def render_subs(ct_id, uid, msg_id=None):
        ct = database.CARGO_TYPES.get(ct_id)
        if not ct:
            bot.send_message(uid, "Материал не найден.");
            return
        subs = ct.get('subcategories') or {}
        text = f"📋 *Подкатегории «{ct['name']}»* ({len(subs)}):\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        if not subs:
            text += "_Пусто._\n"
        else:
            for sid, sname in subs.items():
                m.add(types.InlineKeyboardButton(sname,
                                                 callback_data=f"adm_ct_sub_show|{ct_id}|{sid}"))
        m.add(types.InlineKeyboardButton("➕ Добавить", callback_data=f"adm_ct_sub_add|{ct_id}"))
        m.add(types.InlineKeyboardButton("⬅️ К материалу", callback_data=f"adm_show|ct|{ct_id}"))
        if msg_id:
            try:
                bot.edit_message_text(chat_id=uid, message_id=msg_id, text=text,
                                      parse_mode='Markdown', reply_markup=m)
                return
            except Exception:
                pass
        bot.send_message(uid, text, parse_mode='Markdown', reply_markup=m)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_sub_add|'))
    def cb_adm_ct_sub_add(call):
        if not check(call): return
        ct_id = call.data.split('|', 1)[1]
        state[call.message.chat.id] = {'action': 'add_sub', 'ct_id': ct_id}
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
                         "📋 Введите название подкатегории:\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')

    @bot.message_handler(func=lambda m: state.get(m.chat.id, {}).get('action') == 'add_sub')
    def process_add_sub(message):
        uid = message.chat.id
        st = state.get(uid)
        if not st: return
        text = (message.text or '').strip()
        if text.lower() in ('/cancel', 'отмена'):
            state.pop(uid, None)
            bot.send_message(uid, "❌ Отменено.");
            return
        if len(text) < 2:
            bot.send_message(uid, "❌ Слишком коротко:");
            return
        ct_id = st['ct_id']
        database.add_subcategory(ct_id, text)
        state.pop(uid, None)
        bot.send_message(uid, f"✅ Подкатегория добавлена: {text}")
        render_subs(ct_id, uid)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_sub_show|'))
    def cb_adm_ct_sub_show(call):
        if not check(call): return
        _, ct_id, sub_id = call.data.split('|', 2)
        ct = database.CARGO_TYPES.get(ct_id)
        if not ct:
            bot.answer_callback_query(call.id, "Не найдено.");
            return
        subs = ct.get('subcategories') or {}
        if sub_id not in subs:
            bot.answer_callback_query(call.id, "Не найдено.");
            return
        sub_name = subs[sub_id]
        bot.answer_callback_query(call.id)
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("✏️ Переименовать",
                                         callback_data=f"adm_ct_sub_ren|{ct_id}|{sub_id}"))
        m.add(types.InlineKeyboardButton("🗑 Удалить",
                                         callback_data=f"adm_ct_sub_del|{ct_id}|{sub_id}"))
        m.add(types.InlineKeyboardButton("⬅️ К подкатегориям",
                                         callback_data=f"adm_ct_subs|{ct_id}"))
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=f"📋 *Подкатегория*\n\n{sub_name}",
                                  parse_mode='Markdown', reply_markup=m)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_sub_ren|'))
    def cb_adm_ct_sub_ren(call):
        if not check(call): return
        _, ct_id, sub_id = call.data.split('|', 2)
        state[call.message.chat.id] = {'action': 'edit_sub', 'ct_id': ct_id, 'sub_id': sub_id}
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
                         "✏️ Введите новое название:\n\n_Отмена: /cancel_",
                         parse_mode='Markdown')

    @bot.message_handler(func=lambda m: state.get(m.chat.id, {}).get('action') == 'edit_sub')
    def process_edit_sub(message):
        uid = message.chat.id
        st = state.get(uid)
        if not st: return
        text = (message.text or '').strip()
        if text.lower() in ('/cancel', 'отмена'):
            state.pop(uid, None)
            bot.send_message(uid, "❌ Отменено.");
            return
        if len(text) < 2:
            bot.send_message(uid, "❌ Слишком коротко:");
            return
        database.update_subcategory(st['ct_id'], st['sub_id'], text)
        ct_id = st['ct_id']
        state.pop(uid, None)
        bot.send_message(uid, f"✅ Подкатегория обновлена: {text}")
        render_subs(ct_id, uid)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_sub_del|'))
    def cb_adm_ct_sub_del(call):
        if not check(call): return
        _, ct_id, sub_id = call.data.split('|', 2)
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("✅ Да",
                                       callback_data=f"adm_ct_sub_delconf|{ct_id}|{sub_id}"),
            types.InlineKeyboardButton("⬅️ Нет", callback_data=f"adm_ct_subs|{ct_id}")
        )
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text="⚠️ Удалить подкатегорию?", reply_markup=m)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_ct_sub_delconf|'))
    def cb_adm_ct_sub_delconf(call):
        if not check(call): return
        _, ct_id, sub_id = call.data.split('|', 2)
        database.delete_subcategory(ct_id, sub_id)
        bot.answer_callback_query(call.id, "🗑 Удалено.")
        render_subs(ct_id, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_del|'))
    def cb_adm_del(call):
        if not check(call): return
        _, t, item_id = call.data.split('|', 2)
        m = types.InlineKeyboardMarkup(row_width=2)

        # Возврат для pcat и plat должен вести на список внутри категории
        if t == 'pcat':
            back_cb = f"adm_cat_view|{item_id}"
        elif t == 'plat':
            item = database.PLATFORM_CARGOS.get(item_id, {})
            back_cb = f"adm_cat_view|{item.get('category')}"
        else:
            back_cb = f"adm_show|{t}|{item_id}"

        m.add(
            types.InlineKeyboardButton("✅ Да, удалить",
                                       callback_data=f"adm_delconf|{t}|{item_id}"),
            types.InlineKeyboardButton("⬅️ Нет", callback_data=back_cb)
        )
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=f"⚠️ Удалить запись?\n\n`{item_id}`",
                                  parse_mode='Markdown', reply_markup=m)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith('adm_delconf|'))
    def cb_adm_delconf(call):
        if not check(call): return
        _, t, item_id = call.data.split('|', 2)
        uid = call.message.chat.id

        if t == 'drv':
            database.delete_driver(item_id)
        elif t == 'car':
            database.delete_car(item_id)
        elif t == 'tr':
            database.delete_trailer(item_id)
        elif t == 'loc':
            changed = False
            for m_info in masters_dict.values():
                locs = m_info.get('locations', [])
                if item_id in locs:
                    locs.remove(item_id);
                    changed = True
            if changed:
                try:
                    save_masters_fn()
                except Exception as e:
                    print(f"⚠️ {e}")
            database.delete_location(item_id)
        elif t == 'comp':
            ok, msg = database.delete_company(item_id)
            if not ok:
                bot.answer_callback_query(call.id, f"⛔ {msg}", show_alert=True);
                return
        elif t == 'ct':
            database.delete_cargo_type(item_id)
        elif t == 'cd':
            database.delete_distance(item_id)
        elif t == 'un':
            database.delete_unit(item_id)
        elif t == 'pcat':
            ok, msg = database.delete_platform_category(item_id)
            if not ok:
                bot.answer_callback_query(call.id, f"⛔ {msg}", show_alert=True);
                return
        elif t == 'plat':
            database.delete_platform_cargo(item_id)

        bot.answer_callback_query(call.id, "🗑 Удалено.")
        render_list(t, uid)

    # =========================================================
    # ОДОБРЕНИЕ / ОТКЛОНЕНИЕ НОВЫХ ГРУЗОВ ПЛОЩАДОК
    # =========================================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith('appr_pcargo::'))
    def cb_appr_pcargo(call):
        if not check(call): return
        parts = call.data.split('::')
        cat_id = parts[1]
        msg_id = int(parts[2])
        pending = pending_platform_cargos.pop(msg_id, None)
        if not pending:
            bot.answer_callback_query(call.id, "Уже обработано.");
            return
        database.add_platform_cargo(pending['name'], cat_id)
        bot.answer_callback_query(call.id, "✅ Груз добавлен в справочник.")
        cat_info = database.PLATFORM_CATEGORIES.get(cat_id, {})
        cat_label = f"{cat_info.get('icon', '📦')} {cat_info.get('name', '—')}"
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=f"✅ Груз «{pending['name']}» добавлен ({cat_label}).")
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith('rej_pcargo::'))
    def cb_rej_pcargo(call):
        if not check(call): return
        msg_id = int(call.data.split('::')[1])
        pending = pending_platform_cargos.pop(msg_id, None)
        if not pending:
            bot.answer_callback_query(call.id, "Уже обработано.");
            return
        bot.answer_callback_query(call.id, "❌ Отклонено.")
        try:
            bot.edit_message_text(chat_id=call.message.chat.id,
                                  message_id=call.message.message_id,
                                  text=f"❌ Груз «{pending['name']}» отклонён.")
        except Exception:
            pass

    print("✅ admin_menu зарегистрирован")
# =============================================================
# КЛАВИАТУРЫ
# =============================================================
from telebot import types
from database import (CARS, DRIVERS, TRAILERS, LOCATIONS, COMPANIES,
                      CARGO_TYPES, CARGO_DISTANCES, UNITS,
                      PLATFORM_CARGOS, PLATFORM_CATEGORIES)

def get_main_keyboard():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(types.KeyboardButton("🚛 Я водитель"), types.KeyboardButton("👨‍💼 Я мастер"))
    return m

def get_companies_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for comp_id, comp_info in COMPANIES.items():
        m.add(types.InlineKeyboardButton(f"🏢 {comp_info['name']}", callback_data=f"select_company_{comp_id}"))
    return m

def get_drivers_keyboard(company_id=None):
    m = types.InlineKeyboardMarkup(row_width=1)
    drivers = {k: v for k, v in DRIVERS.items() if v.get('company_id') == company_id} if company_id else DRIVERS
    for drv_id, drv_info in drivers.items():
        m.add(types.InlineKeyboardButton(drv_info['name'], callback_data=f"select_driver_{drv_id}"))
    if company_id:
        m.add(types.InlineKeyboardButton("➕ Я новый — зарегистрироваться", callback_data="reg_new_driver"))
    m.add(types.InlineKeyboardButton("⬅️ Назад к фирмам", callback_data="back_to_companies"))
    return m

def get_cars_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for car_id, car_info in CARS.items():
        ctype = "🚛" if car_info.get('type') == 'tipper' else "🚜"
        m.add(types.InlineKeyboardButton(f"{ctype} {car_info['model']} ({car_info['plate']})", callback_data=f"select_car_{car_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_menu"))
    return m

def get_unit_keyboard(back_action="back_to_qty"):
    m = types.InlineKeyboardMarkup(row_width=2)
    for unit_id, unit_name in UNITS.items():
        m.add(types.InlineKeyboardButton(unit_name, callback_data=f"unit::{unit_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=back_action))
    return m

def get_platform_unit_keyboard():
    m = types.InlineKeyboardMarkup(row_width=2)
    for unit_id, unit_name in UNITS.items():
        m.add(types.InlineKeyboardButton(unit_name, callback_data=f"p_unit::{unit_id}"))
    return m

# --- Клавиатуры для площадок (Категории и Грузы) ---
def get_platform_categories_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_info in PLATFORM_CATEGORIES.items():
        icon = cat_info.get('icon', '📦')
        name = cat_info.get('name', 'Без названия')
        m.add(types.InlineKeyboardButton(f"{icon} {name}", callback_data=f"p_cat::{cat_id}"))
    m.add(types.InlineKeyboardButton("➕ Ввести свой груз", callback_data="p_cargo_custom"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_unloading"))
    return m

def get_platform_cargos_keyboard(category_id):
    m = types.InlineKeyboardMarkup(row_width=1)
    for cid, c in PLATFORM_CARGOS.items():
        if c.get('category') != category_id: continue
        m.add(types.InlineKeyboardButton(c['name'], callback_data=f"p_cargo_name::{cid}"))
    cat = PLATFORM_CATEGORIES.get(category_id, {})
    back_text = f"⬅️ Назад к {cat.get('name', 'категориям')}"
    m.add(types.InlineKeyboardButton(back_text, callback_data="p_cargo_back_cats"))
    return m

def get_platform_new_cargo_category_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_info in PLATFORM_CATEGORIES.items():
        icon = cat_info.get('icon', '📦')
        name = cat_info.get('name', 'Без названия')
        m.add(types.InlineKeyboardButton(f"{icon} Это {name}", callback_data=f"p_newcat::{cat_id}"))
    return m

def get_confirm_car_keyboard():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("✅ Оставить", callback_data="confirm_car_yes"), types.InlineKeyboardButton("🔄 Сменить", callback_data="confirm_car_no"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_drivers"))
    return m

def get_date_keyboard():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("📅 Сегодня", callback_data="date_today"), types.InlineKeyboardButton("📅 Вчера", callback_data="date_yesterday"))
    m.add(types.InlineKeyboardButton("📅 Позавчера", callback_data="date_day_before"), types.InlineKeyboardButton("📅 Другая дата", callback_data="date_other"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_waybill"))
    return m

def get_trailer_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🚫 Без прицепа", callback_data="trailer_none"))
    for tr_id, tr_info in TRAILERS.items():
        m.add(types.InlineKeyboardButton(f"{tr_info['model']} ({tr_info['plate']})", callback_data=f"select_trailer_{tr_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_cars"))
    return m

def get_loading_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for loc_id, loc_info in LOCATIONS.items():
        m.add(types.InlineKeyboardButton(loc_info['name'], callback_data=f"loading_{loc_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_date"))
    return m

def get_unloading_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for loc_id, loc_info in LOCATIONS.items():
        m.add(types.InlineKeyboardButton(loc_info['name'], callback_data=f"unloading_{loc_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_loading"))
    return m

def get_cargo_type_keyboard():
    m = types.InlineKeyboardMarkup(row_width=1)
    for cargo_id, cargo_info in CARGO_TYPES.items():
        m.add(types.InlineKeyboardButton(cargo_info['name'], callback_data=f"cargo_type::{cargo_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_unloading"))
    return m

def get_cargo_subcategory_keyboard(cargo_id):
    m = types.InlineKeyboardMarkup(row_width=1)
    cargo_info = CARGO_TYPES.get(cargo_id, {})
    subcategories = cargo_info.get('subcategories') or {}
    for sub_id, sub_name in subcategories.items():
        m.add(types.InlineKeyboardButton(sub_name, callback_data=f"cargo_sub::{cargo_id}::{sub_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_cargo_type"))
    return m

def get_cargo_distance_keyboard(cargo_id):
    m = types.InlineKeyboardMarkup(row_width=1)
    for dist_id, dist_text in CARGO_DISTANCES.items():
        m.add(types.InlineKeyboardButton(dist_text, callback_data=f"cargo_dist::{cargo_id}::{dist_id}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_sub::{cargo_id}"))
    return m

def get_car_type_keyboard():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🚛 Самосвал", callback_data="car_type_tipper"), types.InlineKeyboardButton("🚜 Площадка (Трал)", callback_data="car_type_platform"))
    return m
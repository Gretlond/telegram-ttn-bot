# ==========================================
# БАЗА ДАННЫХ БОТА (JSON-хранилище)
# ==========================================
from db_store import load_json, save_json, ensure_data_dir, next_id, FILES
import os

# Демонстрационные данные. В production используются файлы из data/,
# которые исключены из репозитория через .gitignore.
_DEFAULT_CARS = {
    "car_1": {"model": "МАЗ 6501С5", "plate": "А000АА-0", "capacity": 20.65, "type": "tipper"},
    "car_2": {"model": "МАЗ 650128", "plate": "А001АА-0", "capacity": 20.05, "type": "tipper"},
    "car_3": {"model": "КАМАЗ 6520", "plate": "А002АА-0", "capacity": 22.00, "type": "tipper"},
}

_DEFAULT_DRIVERS = {
    "drv_1": {"name": "Иванов И.И.", "car_id": "car_1", "company_id": "comp_1"},
    "drv_2": {"name": "Петров П.П.", "car_id": "car_2", "company_id": "comp_1"},
    "drv_3": {"name": "Сидоров С.С.", "car_id": "car_3", "company_id": "comp_1"},
}

_DEFAULT_TRAILERS = {
    "tr_1": {"model": "Прицеп-платформа", "plate": "А100АА-0"},
    "tr_2": {"model": "Самосвальный прицеп", "plate": "А101АА-0"},
}

_DEFAULT_LOCATIONS = {
    "loc_1": {"name": "Площадка №1", "master": "Мастер 1"},
    "loc_2": {"name": "Склад «Северный»", "master": "Мастер 2"},
    "loc_3": {"name": "Объект «Школа»", "master": "Мастер 3"},
}

_DEFAULT_COMPANIES = {
    "comp_1": {"name": "Демо-Строй"},
    "comp_2": {"name": "Демо-Логистика"},
}

_DEFAULT_CARGO_TYPES = {
    "ground": {
        "name": "Грунт",
        "subcategories": {
            "ground_1": "Грунт 1-й категории",
            "ground_2": "Грунт 2-й категории",
            "ground_3": "Грунт 3-й категории",
        },
        "has_distance": True,
    },
    "concrete": {
        "name": "Бетон",
        "subcategories": {
            "concrete_m100": "Бетон М100",
            "concrete_m150": "Бетон М150",
            "concrete_m200": "Бетон М200",
            "concrete_m250": "Бетон М250",
            "concrete_m300": "Бетон М300",
            "concrete_m350": "Бетон М350",
            "concrete_m400": "Бетон М400",
        },
        "has_distance": False,
    },
    "sand":      {"name": "Песок",   "subcategories": {}, "has_distance": False},
    "gravel": {
        "name": "Щебень",
        "subcategories": {
            "gravel_5_20": "Щебень 5-20",
            "gravel_20_40": "Щебень 20-40",
            "gravel_40_70": "Щебень 40-70",
        },
        "has_distance": False,
    },
    "brick":     {"name": "Кирпич",  "subcategories": {}, "has_distance": False},
    "asphalt":   {"name": "Асфальт", "subcategories": {}, "has_distance": False},
}

_DEFAULT_CARGO_DISTANCES = {
    "dist_1": "на расстояние до 1 км",
    "dist_2": "на расстояние до 5 км",
    "dist_3": "на расстояние до 10 км",
    "dist_4": "на расстояние до 20 км",
    "dist_5": "на расстояние свыше 20 км",
}

_DEFAULT_UNITS = {
    "unit_t": "тн",
    "unit_m3": "м³",
    "unit_pcs": "шт",
}

_DEFAULT_PLATFORM_CATEGORIES = {
    "cat_1": {"name": "Техника", "icon": "🚜"},
    "cat_2": {"name": "Материалы", "icon": "🧱"},
}

_DEFAULT_PLATFORM_CARGOS = {
    "p_1": {"name": "Экскаватор", "category": "cat_1"},
    "p_2": {"name": "Плита ПК 60", "category": "cat_2"},
    "p_3": {"name": "Кран", "category": "cat_1"},
    "p_4": {"name": "Бытовка", "category": "cat_2"},
}

# Постоянные реквизиты верхней части ТТН. Значения задаются в кабинете
# администратора и применяются ко всем новым документам.
TTN_HEADER_FIELDS = (
    "shipper", "shipper_unp",
    "consignee", "consignee_unp",
    "customer", "customer_unp",
)
_DEFAULT_TTN_HEADER = {}

CARS = {}
DRIVERS = {}
TRAILERS = {}
LOCATIONS = {}
COMPANIES = {}
CARGO_TYPES = {}
CARGO_DISTANCES = {}
UNITS = {}
PLATFORM_CARGOS = {}
PLATFORM_CATEGORIES = {}
TTN_HEADER = {}

def _ensure_file(name, default):
    ensure_data_dir()
    path = os.path.join("data", FILES[name])
    if not os.path.exists(path):
        save_json(name, default)
        print(f"📁 Создаю {path}")

def _migrate_drivers_companies():
    if not COMPANIES or not DRIVERS: return
    first = next(iter(COMPANIES.keys()))
    changed = False
    for drv in DRIVERS.values():
        if 'company_id' not in drv or not drv['company_id']:
            drv['company_id'] = first; changed = True
    if changed: save_drivers()

def _migrate_cars_type():
    if not CARS: return
    changed = False
    for car in CARS.values():
        if 'type' not in car:
            car['type'] = 'tipper'; changed = True
    if changed: save_cars()

def _migrate_platform_cargos():
    if not PLATFORM_CARGOS: return
    changed = False
    first_cat = next(iter(PLATFORM_CATEGORIES.keys())) if PLATFORM_CATEGORIES else ""
    for c in PLATFORM_CARGOS.values():
        cat = c.get('category', '')
        if cat == 'tech':
            c['category'] = 'cat_1'; changed = True
        elif cat == 'mat':
            c['category'] = 'cat_2'; changed = True
        elif cat not in PLATFORM_CATEGORIES:
            c['category'] = first_cat; changed = True
    if changed: save_platform_cargos()

def reload_all():
    CARS.clear();            CARS.update(load_json("cars", _DEFAULT_CARS))
    DRIVERS.clear();         DRIVERS.update(load_json("drivers", _DEFAULT_DRIVERS))
    TRAILERS.clear();        TRAILERS.update(load_json("trailers", _DEFAULT_TRAILERS))
    LOCATIONS.clear();       LOCATIONS.update(load_json("locations", _DEFAULT_LOCATIONS))
    COMPANIES.clear();       COMPANIES.update(load_json("companies", _DEFAULT_COMPANIES))
    CARGO_TYPES.clear();     CARGO_TYPES.update(load_json("cargo_types", _DEFAULT_CARGO_TYPES))
    CARGO_DISTANCES.clear(); CARGO_DISTANCES.update(load_json("cargo_distances", _DEFAULT_CARGO_DISTANCES))
    UNITS.clear();           UNITS.update(load_json("units", _DEFAULT_UNITS))
    PLATFORM_CATEGORIES.clear(); PLATFORM_CATEGORIES.update(load_json("platform_categories", _DEFAULT_PLATFORM_CATEGORIES))
    PLATFORM_CARGOS.clear(); PLATFORM_CARGOS.update(load_json("platform_cargos", _DEFAULT_PLATFORM_CARGOS))
    TTN_HEADER.clear();    TTN_HEADER.update(load_json("ttn_header", _DEFAULT_TTN_HEADER))
    _migrate_drivers_companies()
    _migrate_cars_type()
    _migrate_platform_cargos()

def save_cars():           return save_json("cars", dict(CARS))
def save_drivers():        return save_json("drivers", dict(DRIVERS))
def save_trailers():       return save_json("trailers", dict(TRAILERS))
def save_locations():      return save_json("locations", dict(LOCATIONS))
def save_companies():      return save_json("companies", dict(COMPANIES))
def save_cargo_types():    return save_json("cargo_types", dict(CARGO_TYPES))
def save_cargo_distances():return save_json("cargo_distances", dict(CARGO_DISTANCES))
def save_units():          return save_json("units", dict(UNITS))
def save_platform_cargos():return save_json("platform_cargos", dict(PLATFORM_CARGOS))
def save_platform_categories(): return save_json("platform_categories", dict(PLATFORM_CATEGORIES))
def save_ttn_header():    return save_json("ttn_header", dict(TTN_HEADER))

def update_ttn_header(**fields):
    """Сохраняет постоянные реквизиты ТТН, введённые администратором."""
    allowed = set(TTN_HEADER_FIELDS)
    if any(key not in allowed for key in fields):
        return False
    for key, value in fields.items():
        TTN_HEADER[key] = str(value or "").strip()
    save_ttn_header(); return True

def init_storage():
    for name, default in [
        ("cars", _DEFAULT_CARS), ("drivers", _DEFAULT_DRIVERS),
        ("trailers", _DEFAULT_TRAILERS), ("locations", _DEFAULT_LOCATIONS),
        ("companies", _DEFAULT_COMPANIES), ("cargo_types", _DEFAULT_CARGO_TYPES),
        ("cargo_distances", _DEFAULT_CARGO_DISTANCES), ("units", _DEFAULT_UNITS),
        ("platform_categories", _DEFAULT_PLATFORM_CATEGORIES),
        ("platform_cargos", _DEFAULT_PLATFORM_CARGOS),
        ("ttn_header", _DEFAULT_TTN_HEADER),
    ]:
        _ensure_file(name, default)
    reload_all()

def add_driver(name, car_id, company_id=""):
    if not company_id and COMPANIES: company_id = next(iter(COMPANIES.keys()))
    drv_id = next_id("drv", DRIVERS)
    DRIVERS[drv_id] = {"name": name, "car_id": car_id or "", "company_id": company_id or ""}
    save_drivers(); return drv_id

def update_driver(drv_id, **fields):
    if drv_id not in DRIVERS: return False
    for k, v in fields.items(): DRIVERS[drv_id][k] = v
    save_drivers(); return True

def delete_driver(drv_id):
    if drv_id not in DRIVERS: return False
    del DRIVERS[drv_id]; save_drivers(); return True

def get_drivers_by_company(company_id):
    return {k: v for k, v in DRIVERS.items() if v.get('company_id') == company_id}

def add_car(model, plate, capacity=20.0, car_type="tipper"):
    car_id = next_id("car", CARS)
    CARS[car_id] = {"model": model, "plate": plate, "capacity": float(capacity), "type": car_type}
    save_cars(); return car_id

def update_car(car_id, **fields):
    if car_id not in CARS: return False
    for k, v in fields.items(): CARS[car_id][k] = v
    save_cars(); return True

def delete_car(car_id):
    if car_id not in CARS: return False
    del CARS[car_id]
    changed = False
    for drv in DRIVERS.values():
        if drv.get("car_id") == car_id:
            drv["car_id"] = ""; changed = True
    if changed: save_drivers()
    save_cars(); return True

def add_trailer(plate, model=""):
    tr_id = next_id("tr", TRAILERS)
    TRAILERS[tr_id] = {"model": model, "plate": plate}
    save_trailers(); return tr_id


def trailer_number(trailer):
    """Номер прицепа без марки — для списков и печатной формы."""
    return (trailer.get("plate") or "").strip() or (trailer.get("model") or "").strip()

def update_trailer(tr_id, **fields):
    if tr_id not in TRAILERS: return False
    for k, v in fields.items(): TRAILERS[tr_id][k] = v
    save_trailers(); return True

def delete_trailer(tr_id):
    if tr_id not in TRAILERS: return False
    del TRAILERS[tr_id]; save_trailers(); return True

def add_location(name, master):
    loc_id = next_id("loc", LOCATIONS)
    LOCATIONS[loc_id] = {"name": name, "master": master}
    save_locations(); return loc_id

def update_location(loc_id, **fields):
    if loc_id not in LOCATIONS: return False
    for k, v in fields.items(): LOCATIONS[loc_id][k] = v
    save_locations(); return True

def delete_location(loc_id):
    if loc_id not in LOCATIONS: return False
    del LOCATIONS[loc_id]; save_locations(); return True

def add_company(name):
    comp_id = next_id("comp", COMPANIES)
    COMPANIES[comp_id] = {"name": name}
    save_companies(); return comp_id

def update_company(comp_id, **fields):
    if comp_id not in COMPANIES: return False
    for k, v in fields.items(): COMPANIES[comp_id][k] = v
    save_companies(); return True

def delete_company(comp_id):
    if comp_id not in COMPANIES: return False, "Компания не найдена."
    drivers_in = [d for d in DRIVERS.values() if d.get('company_id') == comp_id]
    if drivers_in: return False, f"В компании {len(drivers_in)} водителей. Сначала перенесите их."
    if len(COMPANIES) <= 1: return False, "Нельзя удалить единственную компанию."
    del COMPANIES[comp_id]; save_companies(); return True, "Удалено"

def add_cargo_type(name, has_distance=False):
    ct_id = next_id("cargo", CARGO_TYPES)
    CARGO_TYPES[ct_id] = {"name": name, "subcategories": {}, "has_distance": bool(has_distance)}
    save_cargo_types(); return ct_id

def update_cargo_type(ct_id, name=None, has_distance=None):
    if ct_id not in CARGO_TYPES: return False
    if name is not None: CARGO_TYPES[ct_id]['name'] = name
    if has_distance is not None: CARGO_TYPES[ct_id]['has_distance'] = bool(has_distance)
    save_cargo_types(); return True

def delete_cargo_type(ct_id):
    if ct_id not in CARGO_TYPES: return False
    del CARGO_TYPES[ct_id]; save_cargo_types(); return True

def add_subcategory(ct_id, name):
    if ct_id not in CARGO_TYPES: return None
    if not CARGO_TYPES[ct_id].get('subcategories'): CARGO_TYPES[ct_id]['subcategories'] = {}
    sub_id = next_id("sub", CARGO_TYPES[ct_id]['subcategories'])
    CARGO_TYPES[ct_id]['subcategories'][sub_id] = name
    save_cargo_types(); return sub_id

def update_subcategory(ct_id, sub_id, name):
    if ct_id not in CARGO_TYPES: return False
    subs = CARGO_TYPES[ct_id].get('subcategories') or {}
    if sub_id not in subs: return False
    subs[sub_id] = name
    save_cargo_types(); return True

def delete_subcategory(ct_id, sub_id):
    if ct_id not in CARGO_TYPES: return False
    subs = CARGO_TYPES[ct_id].get('subcategories') or {}
    if sub_id not in subs: return False
    del subs[sub_id]; save_cargo_types(); return True

def add_distance(text):
    d_id = next_id("dist", CARGO_DISTANCES)
    CARGO_DISTANCES[d_id] = text; save_cargo_distances(); return d_id

def update_distance(d_id, text):
    if d_id not in CARGO_DISTANCES: return False
    CARGO_DISTANCES[d_id] = text; save_cargo_distances(); return True

def delete_distance(d_id):
    if d_id not in CARGO_DISTANCES: return False
    del CARGO_DISTANCES[d_id]; save_cargo_distances(); return True

def add_unit(name):
    u_id = next_id("unit", UNITS)
    UNITS[u_id] = name; save_units(); return u_id

def update_unit(u_id, name):
    if u_id not in UNITS: return False
    UNITS[u_id] = name; save_units(); return True

def delete_unit(u_id):
    if u_id not in UNITS: return False
    del UNITS[u_id]; save_units(); return True

# --- Категории площадок ---
def add_platform_category(name, icon="📦"):
    cat_id = next_id("cat", PLATFORM_CATEGORIES)
    PLATFORM_CATEGORIES[cat_id] = {"name": name, "icon": icon}
    save_platform_categories(); return cat_id

def update_platform_category(cat_id, name=None, icon=None):
    if cat_id not in PLATFORM_CATEGORIES: return False
    if name is not None: PLATFORM_CATEGORIES[cat_id]['name'] = name
    if icon is not None: PLATFORM_CATEGORIES[cat_id]['icon'] = icon
    save_platform_categories(); return True

def delete_platform_category(cat_id):
    if cat_id not in PLATFORM_CATEGORIES: return False, "Категория не найдена."
    cargos_in = [c for c in PLATFORM_CARGOS.values() if c.get('category') == cat_id]
    if cargos_in: return False, f"В категории {len(cargos_in)} грузов. Сначала удалите их."
    if len(PLATFORM_CATEGORIES) <= 1: return False, "Нельзя удалить единственную категорию."
    del PLATFORM_CATEGORIES[cat_id]
    save_platform_categories()
    return True, "Удалено"

def add_platform_cargo(name, category="cat_1"):
    p_id = next_id("p_cargo", PLATFORM_CARGOS)
    PLATFORM_CARGOS[p_id] = {"name": name, "category": category}
    save_platform_cargos(); return p_id

def update_platform_cargo(p_id, name=None, category=None):
    if p_id not in PLATFORM_CARGOS: return False
    if name is not None: PLATFORM_CARGOS[p_id]['name'] = name
    if category is not None: PLATFORM_CARGOS[p_id]['category'] = category
    save_platform_cargos(); return True

def delete_platform_cargo(p_id):
    if p_id not in PLATFORM_CARGOS: return False
    del PLATFORM_CARGOS[p_id]; save_platform_cargos(); return True

init_storage()
print(f"✅ database загружена: машин={len(CARS)}, водителей={len(DRIVERS)}, ...")
# =============================================================
# JSON-ХРАНИЛИЩЕ ДЛЯ СПРАВОЧНИКОВ
# =============================================================
import os
import json

DATA_DIR = "data"

FILES = {
    "cars": "cars.json",
    "drivers": "drivers.json",
    "trailers": "trailers.json",
    "locations": "locations.json",
    "companies": "companies.json",
    "cargo_types": "cargo_types.json",
    "cargo_distances": "cargo_distances.json",
    "units": "units.json",
    "platform_cargos": "platform_cargos.json",
    "platform_categories": "platform_categories.json",
}

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_json(name, default=None):
    ensure_data_dir()
    path = os.path.join(DATA_DIR, FILES[name])
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Не удалось загрузить {path}: {e}")
        return default if default is not None else {}

def save_json(name, data):
    ensure_data_dir()
    path = os.path.join(DATA_DIR, FILES[name])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ Не удалось сохранить {path}: {e}")
        return False

def next_id(prefix, existing):
    n = 1
    while f"{prefix}_{n}" in existing:
        n += 1
    return f"{prefix}_{n}"
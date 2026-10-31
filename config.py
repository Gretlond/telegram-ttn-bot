# =============================================================
# ОБЩИЕ НАСТРОЙКИ, БОТ, ГЛОБАЛЬНЫЕ СЛОВАРИ
# =============================================================
import os
import json
import telebot
from database import LOCATIONS

from log_setup import get_logger

logger = get_logger(__name__)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
YOUR_TELEGRAM_ID = int(os.environ.get('YOUR_TELEGRAM_ID', '0'))
MASTERS_FILE = os.environ.get("MASTERS_FILE", "masters.json")
LAST_ORDERS_FILE = os.environ.get("LAST_ORDERS_FILE", "last_orders.json")
REGISTRY_MASTER_NAME = os.environ.get('REGISTRY_MASTER_NAME', 'Мастер')

bot = telebot.TeleBot(BOT_TOKEN)

# Глобальные состояния
user_data = {}
last_orders = {}
calculation_state = {}
master_edit_state = {}
pending_masters = {}
pending_drivers = {}
MASTERS = {}

# Состояния для площадок
pending_platform_cargos = {} # {msg_id: {"name": ..., "category": ...}}

def save_masters():
    try:
        with open(MASTERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in MASTERS.items()}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception(f"⚠️ save_masters: {e}")

def load_masters():
    data = {}
    if os.path.exists(MASTERS_FILE):
        try:
            with open(MASTERS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data = {int(k): v for k, v in raw.items()}
            logger.info(f"✅ Загружено мастеров: {len(data)}")
        except Exception as e:
            logger.exception(f"⚠️ load_masters: {e}")
            data = {}
    if YOUR_TELEGRAM_ID not in data:
        data[YOUR_TELEGRAM_ID] = {
            "name": "Администратор",
            "locations": list(LOCATIONS.keys())
        }
    data = {int(k): v for k, v in data.items()}
    MASTERS.clear()
    MASTERS.update(data)
    save_masters()

def save_last_orders():
    try:
        with open(LAST_ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in last_orders.items()}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception(f"⚠️ save_last_orders: {e}")

def load_last_orders():
    loaded = {}
    if os.path.exists(LAST_ORDERS_FILE):
        try:
            with open(LAST_ORDERS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            loaded = {int(k): v for k, v in raw.items()}
            logger.info(f"✅ Загружено last_orders: {len(loaded)}")
        except Exception as e:
            logger.exception(f"⚠️ load_last_orders: {e}")
            loaded = {}
    last_orders.clear()
    last_orders.update(loaded)

load_masters()
load_last_orders()
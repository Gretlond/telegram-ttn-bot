import os
import tempfile

# Тесты не должны создавать рабочие лог-файлы и засорять вывод.
os.environ.setdefault("TTN_LOG_TO_FILE", "0")
os.environ.setdefault("TTN_LOG_LEVEL", "WARNING")

# Изолируем рабочие файлы от production ещё до импорта модулей бота:
# config.py читает masters.json/last_orders.json, orders_db.py — TTN_DB_FILE.
_runtime = tempfile.mkdtemp(prefix="ttn_pytest_")
os.environ["MASTERS_FILE"] = os.path.join(_runtime, "masters.json")
os.environ["LAST_ORDERS_FILE"] = os.path.join(_runtime, "last_orders.json")
os.environ["TTN_DB_FILE"] = os.path.join(_runtime, "orders.db")

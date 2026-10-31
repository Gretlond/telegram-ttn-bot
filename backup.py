# =============================================================
# РЕЗЕРВНОЕ КОПИРОВАНИЕ, ПРОВЕРКА И ВОССТАНОВЛЕНИЕ
# =============================================================
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

from log_setup import get_logger

logger = get_logger(__name__)
BACKUP_DIR = "backup"
MAX_BACKUPS = 30
DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ensure_dir(path, mode=0o700):
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _sqlite_backup(src_path, dst_path):
    """Согласованная копия SQLite через backup API (учитывает WAL)."""
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()


def _copy_json_tree(src_dir, dst_dir):
    if not os.path.isdir(src_dir):
        return
    _ensure_dir(dst_dir)
    for name in sorted(os.listdir(src_dir)):
        src_path = os.path.join(src_dir, name)
        if os.path.isfile(src_path) and name.endswith(".json"):
            shutil.copy2(src_path, os.path.join(dst_dir, name))


def make_backup(include_env=False):
    """Создаёт backup/YYYY-MM-DD/ с БД, JSON и (опционально) .env."""
    _ensure_dir(BACKUP_DIR, 0o700)
    date_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(BACKUP_DIR, date_str)
    _ensure_dir(target_dir, 0o700)

    if os.path.exists("orders.db"):
        _sqlite_backup("orders.db", os.path.join(target_dir, "orders.db"))
    else:
        logger.warning("⚠️ orders.db не найден — копирую только JSON")

    _copy_json_tree("data", os.path.join(target_dir, "data"))

    for name in ("masters.json", "last_orders.json"):
        if os.path.exists(name):
            shutil.copy2(name, os.path.join(target_dir, name))

    if include_env and os.path.exists(".env"):
        shutil.copy2(".env", os.path.join(target_dir, ".env"))
        try:
            os.chmod(os.path.join(target_dir, ".env"), 0o600)
        except OSError:
            pass

    logger.info(f"💾 Резервная копия создана: {target_dir}")
    cleanup_old_backups()
    return target_dir


def verify_backup(path):
    """Проверяет целостность БД и JSON. Возвращает список ошибок."""
    errors = []
    if not os.path.isdir(path):
        return [f"Каталог не найден: {path}"]

    db_path = os.path.join(path, "orders.db")
    if not os.path.exists(db_path):
        errors.append("нет orders.db")
    else:
        try:
            conn = sqlite3.connect(db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if not result or result[0] != "ok":
                errors.append(f"integrity_check: {result[0] if result else 'нет ответа'}")
        except Exception as e:
            errors.append(f"orders.db: {e}")

    json_files = []
    data_dir = os.path.join(path, "data")
    if os.path.isdir(data_dir):
        json_files.extend(os.path.join(data_dir, n) for n in os.listdir(data_dir)
                          if n.endswith(".json"))
    for name in ("masters.json", "last_orders.json"):
        json_files.append(os.path.join(path, name))

    for json_path in json_files:
        if not os.path.exists(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            errors.append(f"{os.path.relpath(json_path, path)}: {e}")

    return errors


def restore_backup(source_dir, assume_yes=False):
    """Восстанавливает БД и JSON. Требует подтверждения и создаёт safety-копию."""
    errors = verify_backup(source_dir)
    if errors:
        raise RuntimeError("Копия не прошла проверку: " + "; ".join(errors))

    logger.warning("⚠️ Бот должен быть остановлен перед восстановлением.")
    if not assume_yes:
        answer = input("Введите ВОССТАНОВИТЬ для продолжения: ").strip()
        if answer != "ВОССТАНОВИТЬ":
            logger.info("Отменено.")
            return False

    safety_dir = os.path.join(
        BACKUP_DIR, "_pre_restore_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    _ensure_dir(safety_dir, 0o700)
    if os.path.exists("orders.db"):
        _sqlite_backup("orders.db", os.path.join(safety_dir, "orders.db"))
    for name in ("masters.json", "last_orders.json"):
        if os.path.exists(name):
            shutil.copy2(name, os.path.join(safety_dir, name))
    logger.info(f"🛟 Страховочная копия: {safety_dir}")

    source_db = os.path.join(source_dir, "orders.db")
    if os.path.exists(source_db):
        _sqlite_backup(source_db, "orders.db")

    source_data = os.path.join(source_dir, "data")
    if os.path.isdir(source_data):
        _ensure_dir("data")
        for name in os.listdir(source_data):
            if name.endswith(".json"):
                shutil.copy2(os.path.join(source_data, name),
                             os.path.join("data", name))

    for name in ("masters.json", "last_orders.json"):
        src = os.path.join(source_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, name)

    if os.path.exists(os.path.join(source_dir, ".env")):
        shutil.copy2(os.path.join(source_dir, ".env"), ".env")
        try:
            os.chmod(".env", 0o600)
        except OSError:
            pass

    logger.info(f"✅ Восстановлено из: {source_dir}")
    return True


def cleanup_old_backups():
    """Удаляет старые ежедневные копии, оставляя последние MAX_BACKUPS."""
    if not os.path.exists(BACKUP_DIR):
        return
    dirs = sorted(
        d for d in os.listdir(BACKUP_DIR)
        if DATE_DIR_RE.match(d) and os.path.isdir(os.path.join(BACKUP_DIR, d))
    )
    for old in dirs[:-MAX_BACKUPS]:
        try:
            shutil.rmtree(os.path.join(BACKUP_DIR, old))
            logger.info(f"🗑 Удалена старая копия: {old}")
        except Exception as e:
            logger.exception(f"⚠️ Не удалить {old}: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backup / verify / restore TTN bot data")
    parser.add_argument("--verify", metavar="DIR", help="проверить копию")
    parser.add_argument("--restore", metavar="DIR", help="восстановить из копии")
    parser.add_argument("--yes", action="store_true", help="без интерактивного подтверждения")
    parser.add_argument("--include-env", action="store_true", help="включить .env в копию")
    args = parser.parse_args(argv)

    if args.verify:
        errors = verify_backup(args.verify)
        if errors:
            logger.error("❌ Ошибка проверки: " + "; ".join(errors))
            return 1
        logger.info(f"✅ Копия корректна: {args.verify}")
        return 0

    if args.restore:
        restore_backup(args.restore, assume_yes=args.yes)
        return 0

    target = make_backup(include_env=args.include_env)
    errors = verify_backup(target)
    if errors:
        logger.error("❌ Копия создана, но проверка не прошла: " + "; ".join(errors))
        return 1
    logger.info(f"✅ Проверка копии пройдена: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

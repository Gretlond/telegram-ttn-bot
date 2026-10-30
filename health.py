# =============================================================
# СОСТОЯНИЕ БОТА: МАСТЕРА, ДОСТАВКА, БЭКАПЫ
# =============================================================
import os
import re
from datetime import datetime

import backup
import orders_db

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def human_size(size):
    size = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


def check_master_chat(bot, master_id):
    """Проверяет, может ли бот получить чат мастера."""
    try:
        chat = bot.get_chat(int(master_id))
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "chat_name": ""}

    if isinstance(chat, dict):
        name = chat.get("first_name") or chat.get("title") or ""
        username = chat.get("username") or ""
    else:
        name = (getattr(chat, "first_name", None)
                or getattr(chat, "title", None) or "")
        username = getattr(chat, "username", None) or ""
    return {
        "ok": True,
        "error": "",
        "chat_name": name,
        "username": username,
    }


def check_masters(bot, masters, locations=None):
    locations = locations or {}
    result = []
    for master_id, info in masters.items():
        try:
            mid = int(master_id)
        except (TypeError, ValueError):
            continue
        check = check_master_chat(bot, mid)
        result.append({
            "id": mid,
            "name": (info or {}).get("name", "—"),
            "locations": [
                (locations.get(loc_id) or {}).get("name", loc_id)
                for loc_id in (info or {}).get("locations", [])
            ],
            **check,
        })
    return result


def get_database_info(db_file=None):
    path = db_file or orders_db.DB_FILE
    if not os.path.exists(path):
        return {"path": path, "exists": False, "size": 0}
    return {
        "path": path,
        "exists": True,
        "size": os.path.getsize(path),
        "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime(
            "%Y-%m-%d %H:%M:%S"),
    }


def get_active_batches():
    conn = orders_db.get_connection()
    rows = conn.execute(
        """SELECT b.*, COUNT(o.id) AS assigned
           FROM batches b
           LEFT JOIN orders o ON o.batch_id = b.id AND o.deleted_at IS NULL
           WHERE b.closed_at IS NULL
           GROUP BY b.id
           ORDER BY b.id DESC"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_backup(backup_dir=None):
    folder = backup_dir or backup.BACKUP_DIR
    if not os.path.isdir(folder):
        return None
    try:
        candidates = [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if DATE_DIR_RE.match(name)
            and os.path.isdir(os.path.join(folder, name))
        ]
    except OSError:
        return None
    if not candidates:
        return None
    path = max(candidates, key=lambda item: os.path.getmtime(item))
    errors = backup.verify_backup(path)
    return {
        "path": path,
        "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime(
            "%Y-%m-%d %H:%M:%S"),
        "errors": errors,
    }


def _delivery_lines():
    counts = orders_db.get_delivery_counts()
    failed = counts.get("failed", 0)
    pending = counts.get("pending", 0)
    delivered = counts.get("delivered", 0)
    unknown = counts.get("unknown", 0)
    lines = [
        f"Доставка: доставлено {delivered}, ошибки {failed}, ожидают {pending}",
    ]
    if unknown:
        lines.append(f"Исторические заявки без статуса: {unknown}")
    undelivered = orders_db.get_undelivered_orders(limit=5)
    if undelivered:
        lines.append("Недоставленные:")
        for order in undelivered:
            status = order.get("delivery_status") or "unknown"
            error = (order.get("delivery_error") or "").strip()
            if len(error) > 80:
                error = error[:77] + "..."
            suffix = f" — {error}" if error else ""
            lines.append(
                f"  №{order['id']} мастер {order.get('master_id')}: "
                f"{status}{suffix}")
    return lines


def build_status_text(master_checks, db_file=None, backup_dir=None):
    lines = ["🩺 Состояние бота", ""]

    db = get_database_info(db_file)
    if db.get("exists"):
        lines.append(f"База: {human_size(db['size'])} ({db['mtime']})")
    else:
        lines.append(f"База: файл не найден ({db['path']})")

    try:
        batches = get_active_batches()
    except Exception as e:
        lines.append(f"Активные пачки: ошибка чтения БД ({e})")
    else:
        if batches:
            lines.append(f"Активные пачки: {len(batches)}")
            for batch in batches:
                lines.append(
                    f"  №{batch['id']}: {batch.get('counter', 0)}/25, "
                    f"верхний {batch.get('start_number')}")
        else:
            lines.append("Активные пачки: нет")

    try:
        lines.extend(_delivery_lines())
    except Exception as e:
        lines.append(f"Доставка: ошибка чтения БД ({e})")

    last_backup = get_last_backup(backup_dir)
    if last_backup:
        state = "✅ проверен" if not last_backup["errors"] else "⚠️ ошибки"
        lines.append(
            f"Последний бэкап: {last_backup['mtime']} — {state}")
        if last_backup["errors"]:
            lines.append("  " + "; ".join(last_backup["errors"])[:300])
    else:
        lines.append("Последний бэкап: не найден")

    lines.append("")
    lines.append("Мастера:")
    if not master_checks:
        lines.append("  нет записей")
    for master in master_checks:
        mark = "✅" if master.get("ok") else "❌"
        locations = ", ".join(master.get("locations") or []) or "без площадок"
        lines.append(f"  {mark} {master['id']} — {master['name']} ({locations})")
        if not master.get("ok"):
            lines.append(f"     {master.get('error', 'нет связи')}")
    return "\n".join(lines)

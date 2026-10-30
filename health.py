# =============================================================
# СОСТОЯНИЕ БОТА: МАСТЕРА, ДОСТАВКА, БЭКАПЫ
# =============================================================
import os
import re
import subprocess
from datetime import datetime

import backup
import orders_db

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BACKUP_TIMER_UNIT = "ttn_backup.timer"
BACKUP_MAX_AGE_HOURS = 48


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
    mtime = os.path.getmtime(path)
    age_hours = max(0.0, (datetime.now().timestamp() - mtime) / 3600.0)
    errors = backup.verify_backup(path)
    return {
        "path": path,
        "mtime": datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M:%S"),
        "age_hours": age_hours,
        "errors": errors,
    }


def get_backup_timer_status():
    """Статус systemd-таймера автобэкапа без запуска самих копий."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", BACKUP_TIMER_UNIT],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return "unknown"
    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return "unknown"
    return output.splitlines()[0].strip()


def get_backup_monitor(backup_dir=None, timer_status=None):
    """Сводка по автобэкапу: таймер, последняя копия и проблемы."""
    if timer_status is None:
        timer_status = get_backup_timer_status()
    info = get_last_backup(backup_dir)
    issues = []
    if timer_status != "active":
        issues.append(
            f"таймер автобэкапа {BACKUP_TIMER_UNIT} не активен "
            f"({timer_status})")
    if not info:
        issues.append("резервная копия не найдена")
    else:
        if info.get("errors"):
            issues.append("последняя копия не прошла проверку: "
                          + "; ".join(info["errors"])[:200])
        if info.get("age_hours", 0) > BACKUP_MAX_AGE_HOURS:
            age = int(round(info["age_hours"]))
            issues.append(f"последняя копия старше {BACKUP_MAX_AGE_HOURS} ч "
                          f"({age} ч назад)")
    return {
        "timer_status": timer_status,
        "backup": info,
        "issues": issues,
    }


def get_backup_alert(backup_dir=None, timer_status=None):
    """Текст предупреждения для администратора или None, если всё в порядке."""
    monitor = get_backup_monitor(backup_dir, timer_status=timer_status)
    if not monitor["issues"]:
        return None
    lines = ["⚠️ Мониторинг резервных копий"]
    for issue in monitor["issues"]:
        lines.append(f"• {issue}")
    lines.append("")
    lines.append("Проверьте автобэкап: systemctl status ttn_backup.service")
    return "\n".join(lines)


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


def build_status_text(master_checks, db_file=None, backup_dir=None,
                      timer_status=None):
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

    monitor = get_backup_monitor(backup_dir, timer_status=timer_status)
    timer_labels = {
        "active": "✅ активен",
        "inactive": "❌ не активен",
        "failed": "❌ ошибка",
        "activating": "⏳ запускается",
        "unknown": "⚠️ неизвестно",
    }
    lines.append(
        f"Автобэкап: {timer_labels.get(monitor['timer_status'], '⚠️ ошибка')} "
        f"({monitor['timer_status']})")
    last_backup = monitor["backup"]
    if last_backup:
        state = "✅ проверен" if not last_backup["errors"] else "⚠️ ошибки"
        age = int(round(last_backup.get("age_hours", 0)))
        lines.append(
            f"Последний бэкап: {last_backup['mtime']} — {state}, "
            f"{age} ч назад")
        if last_backup["errors"]:
            lines.append("  " + "; ".join(last_backup["errors"])[:300])
    else:
        lines.append("Последний бэкап: не найден")
    if monitor["issues"]:
        lines.append("⚠️ Проблемы автобэкапа:")
        for issue in monitor["issues"]:
            lines.append(f"  • {issue}")

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

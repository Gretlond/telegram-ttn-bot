# =============================================================
# РАБОТА С БАЗОЙ ДАННЫХ ЗАЯВОК (SQLite)
# =============================================================
import sqlite3
import json
import os
from datetime import datetime

from log_setup import get_logger
from pricing import calculate_cargo_cost

logger = get_logger(__name__)
DB_FILE = os.environ.get("TTN_DB_FILE", "orders.db")
BATCH_SIZE = 25

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER, driver_id INTEGER, driver_name TEXT,
            waybill_number TEXT, date TEXT, car_model TEXT, car_plate TEXT,
            trailer_info TEXT, loading_point TEXT, unloading_point TEXT,
            shipper_handed_by TEXT, consignee_received_by TEXT,
            release_allowed_by TEXT, cargo_accepted_by TEXT,
            cargo_json TEXT, status TEXT DEFAULT 'new',
            total_cost REAL DEFAULT 0, total_with_vat REAL DEFAULT 0,
            created_at TEXT, printed_at TEXT, master_message_id INTEGER,
            ttn_number TEXT, batch_id INTEGER, order_row INTEGER,
            delivery_status TEXT DEFAULT 'unknown', delivery_error TEXT,
            delivered_at TEXT, deleted_at TEXT, deleted_by INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER, start_number TEXT,
            counter INTEGER DEFAULT 0, started_at TEXT, closed_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manual_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            ttn_number TEXT NOT NULL,
            date TEXT, loading_point TEXT, driver_name TEXT,
            car_plate TEXT, target_row INTEGER, created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            actor_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            master_id INTEGER NOT NULL,
            granted_by INTEGER,
            granted_at TEXT,
            UNIQUE(order_id, master_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_order ON order_events(order_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_batch ON manual_registry(master_id, batch_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_master ON order_access(master_id, order_id)")
    conn.commit()

    cursor.execute("PRAGMA table_info(orders)")
    existing = {row[1] for row in cursor.fetchall()}
    for col, sql in [
        ("driver_name","ALTER TABLE orders ADD COLUMN driver_name TEXT"),
        ("shipper_handed_by","ALTER TABLE orders ADD COLUMN shipper_handed_by TEXT"),
        ("consignee_received_by","ALTER TABLE orders ADD COLUMN consignee_received_by TEXT"),
        ("release_allowed_by","ALTER TABLE orders ADD COLUMN release_allowed_by TEXT"),
        ("cargo_accepted_by","ALTER TABLE orders ADD COLUMN cargo_accepted_by TEXT"),
        ("master_message_id","ALTER TABLE orders ADD COLUMN master_message_id INTEGER"),
        ("ttn_number","ALTER TABLE orders ADD COLUMN ttn_number TEXT"),
        ("batch_id","ALTER TABLE orders ADD COLUMN batch_id INTEGER"),
        ("order_row","ALTER TABLE orders ADD COLUMN order_row INTEGER"),
        ("delivery_status",
         "ALTER TABLE orders ADD COLUMN delivery_status TEXT DEFAULT 'unknown'"),
        ("delivery_error","ALTER TABLE orders ADD COLUMN delivery_error TEXT"),
        ("delivered_at","ALTER TABLE orders ADD COLUMN delivered_at TEXT"),
        ("deleted_at","ALTER TABLE orders ADD COLUMN deleted_at TEXT"),
        ("deleted_by","ALTER TABLE orders ADD COLUMN deleted_by INTEGER"),
    ]:
        if col not in existing:
            logger.info(f"➕ Миграция: orders.{col}")
            try: cursor.execute(sql); conn.commit()
            except Exception as e: logger.exception(f"⚠️ {e}")

    # WAL уменьшает блокировки при одновременной работе водителей и мастеров.
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        logger.exception(f"⚠️ Не удалось включить WAL: {e}")

    # Старые ручные накладные не увеличивали счётчик пачки. Синхронизируем
    # его с фактически занятыми строками, чтобы предпросмотр пакета не
    # начинался поверх уже введённых ТТН.
    try:
        open_batches = cursor.execute(
            "SELECT id FROM batches WHERE closed_at IS NULL").fetchall()
        for row in open_batches:
            _recalc_counter(conn, int(row[0]))
        conn.commit()
    except Exception as e:
        logger.exception(f"⚠️ Не удалось синхронизировать счётчики пачек: {e}")

    conn.close()


def _event_details(details):
    if details is None:
        return ''
    if isinstance(details, str):
        return details
    try:
        return json.dumps(details, ensure_ascii=False)
    except Exception:
        return str(details)


def log_order_event(order_id, actor_id, action, details=None):
    """Пишет событие в журнал. Ошибка аудита не должна ломать основную операцию."""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO order_events (order_id, actor_id, action, details, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, actor_id, action, _event_details(details),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.exception(f"⚠️ Не удалось записать событие аудита: {e}")


def get_order_events(order_id, limit=50):
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM order_events WHERE order_id = ?
           ORDER BY id DESC LIMIT ?""",
        (order_id, int(limit)),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_events(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM order_events ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_order(data, master_id, driver_id, master_message_id=None):
    conn = get_connection(); cursor = conn.cursor()
    master_id = int(master_id); driver_id = int(driver_id)
    date_str = f"{data.get('day','00')}.{data.get('month','00')}.{data.get('year','00')}"
    cargos_json = json.dumps(data.get('cargos', []), ensure_ascii=False)
    cursor.execute("""
        INSERT INTO orders
        (master_id, driver_id, driver_name, waybill_number, date, car_model, car_plate,
         trailer_info, loading_point, unloading_point, shipper_handed_by,
         consignee_received_by, release_allowed_by, cargo_accepted_by,
         cargo_json, status, created_at, master_message_id, delivery_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, 'pending')
    """, (master_id, driver_id,
          data.get('driver_name',''), data.get('waybill_number',''), date_str,
          data.get('car_model',''), data.get('car_plate',''),
          data.get('trailer_info','-'), data.get('loading_point',''),
          data.get('unloading_point',''), data.get('shipper_handed_by',''),
          data.get('consignee_received_by',''),
          data.get('release_allowed_by', os.environ.get('RELEASE_ALLOWED_BY', 'Руководитель')),
          data.get('cargo_accepted_by',''), cargos_json,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), master_message_id))
    order_id = cursor.lastrowid
    conn.commit(); conn.close()
    log_order_event(order_id, driver_id, 'created', {
        'master_id': master_id,
        'waybill_number': data.get('waybill_number', ''),
    })
    logger.info(f"✅ Заявка сохранена: order_id={order_id}")
    return order_id

def get_order(order_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone(); conn.close()
    return dict(row) if row else None

def get_master_orders(master_id, status=None):
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    query = """SELECT o.*,
                      CASE WHEN o.master_id = ? THEN 0 ELSE 1 END AS is_shared
               FROM orders o
               WHERE o.deleted_at IS NULL
                 AND (o.master_id = ? OR o.id IN (
                     SELECT order_id FROM order_access WHERE master_id = ?))"""
    params = [master_id, master_id, master_id]
    if status:
        query += " AND o.status = ?"
        params.append(status)
    query += " ORDER BY o.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_recent_orders(limit=15):
    """Последние неудалённые заявки для админских экранов."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM orders
           WHERE deleted_at IS NULL
           ORDER BY id DESC LIMIT ?""",
        (int(limit),))
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def grant_order_access(order_id, master_id, granted_by=None):
    """Открывает мастеру доступ к чужой заявке. True — если доступ новый."""
    order = get_order(order_id)
    if not order or order.get('deleted_at'):
        raise ValueError("Заявка не найдена или удалена")
    master_id = int(master_id)
    if int(order.get('master_id') or 0) == master_id:
        return False
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """INSERT OR IGNORE INTO order_access
           (order_id, master_id, granted_by, granted_at)
           VALUES (?, ?, ?, ?)""",
        (int(order_id), master_id,
         int(granted_by) if granted_by is not None else None,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    changed = cursor.rowcount > 0
    conn.commit(); conn.close()
    if changed:
        log_order_event(order_id, granted_by, 'access_granted',
                        {'master_id': master_id})
    return changed


def revoke_order_access(order_id, master_id, revoked_by=None):
    """Закрывает доступ мастера к заявке. True — если доступ был."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM order_access WHERE order_id = ? AND master_id = ?",
        (int(order_id), int(master_id)))
    changed = cursor.rowcount > 0
    conn.commit(); conn.close()
    if changed:
        log_order_event(order_id, revoked_by, 'access_revoked',
                        {'master_id': int(master_id)})
    return changed


def get_order_access(order_id):
    """Список id мастеров, которым открыт доступ к заявке."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        "SELECT master_id FROM order_access WHERE order_id = ? "
        "ORDER BY master_id", (int(order_id),))
    rows = cursor.fetchall(); conn.close()
    return [int(row["master_id"]) for row in rows]


def can_access_order(order_or_id, master_id):
    """Владелец или мастер с выданным доступом может работать с заявкой."""
    try:
        master_id = int(master_id)
    except (TypeError, ValueError):
        return False
    if isinstance(order_or_id, dict):
        order = order_or_id
    else:
        order = get_order(order_or_id)
    if not order or order.get('deleted_at'):
        return False
    if int(order.get('master_id') or 0) == master_id:
        return True
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM order_access WHERE order_id = ? AND master_id = ?",
        (int(order['id']), master_id))
    found = cursor.fetchone() is not None
    conn.close()
    return found

def get_driver_orders_current_month(driver_id):
    """Возвращает заявки водителя за текущий месяц (по дате заявки)."""
    now = datetime.now()
    month_year = now.strftime("%m.%y")  # Например "10.26"
    pattern = f"%.{month_year}"
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM orders
           WHERE driver_id = ? AND date LIKE ? AND deleted_at IS NULL
           ORDER BY id DESC""",
        (int(driver_id), pattern))
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]

def get_cargos(order_id):
    order = get_order(order_id)
    if not order: return []
    try: return json.loads(order['cargo_json'] or '[]')
    except Exception: return []

def update_order_field(order_id, field, value, actor_id=None):
    allowed = {'waybill_number','date','car_model','car_plate','trailer_info',
               'loading_point','unloading_point','status','total_cost','total_with_vat',
               'printed_at','shipper_handed_by','consignee_received_by',
               'release_allowed_by','cargo_accepted_by','ttn_number','batch_id','order_row',
               'master_message_id'}
    if field not in allowed:
        logger.info(f"Недопустимое поле: {field}"); return
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(f"UPDATE orders SET {field} = ? WHERE id = ?", (value, order_id))
    conn.commit(); conn.close()
    if actor_id is not None:
        log_order_event(order_id, actor_id, 'field_updated',
                        {'field': field, 'value': value})

def save_cargos(order_id, cargos, actor_id=None):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE orders SET cargo_json = ? WHERE id = ?",
                   (json.dumps(cargos, ensure_ascii=False), order_id))
    conn.commit(); conn.close()
    if actor_id is not None:
        items = []
        for cargo in cargos or []:
            items.append({
                'name': cargo.get('cargo_name', ''),
                'qty': cargo.get('quantity', cargo.get('cargo_qty', '')),
                'places': cargo.get('places', ''),
            })
        log_order_event(order_id, actor_id, 'cargos_updated',
                        {'count': len(items), 'items': items})


def soft_delete_order(order_id, actor_id, reason=''):
    """Помечает заявку удалённой, сохраняя её и историю для аудита."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders
           SET deleted_at = ?, deleted_by = ?, status = 'deleted'
           WHERE id = ? AND deleted_at IS NULL""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actor_id, order_id))
    changed = cursor.rowcount
    conn.commit(); conn.close()
    if changed:
        log_order_event(order_id, actor_id, 'deleted', {'reason': reason})
    return bool(changed)


def get_deleted_orders(limit=30):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM orders
           WHERE deleted_at IS NOT NULL
           ORDER BY deleted_at DESC LIMIT ?""",
        (int(limit),),
    )
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def restore_order(order_id, actor_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders
           SET deleted_at = NULL, deleted_by = NULL, status = 'new'
           WHERE id = ? AND deleted_at IS NOT NULL""",
        (order_id,))
    changed = cursor.rowcount
    conn.commit(); conn.close()
    if changed:
        log_order_event(order_id, actor_id, 'restored', {})
    return bool(changed)

def recalculate_order_totals(order_id):
    cargos = get_cargos(order_id)
    total_cost = 0.0; total_with_vat = 0.0
    for c in cargos:
        cost = calculate_cargo_cost(c)
        vat = round(cost * 0.20, 2) if c.get('vat_rate') == '20%' else 0.0
        total_cost += cost; total_with_vat += cost + vat
    total_cost = round(total_cost, 2); total_with_vat = round(total_with_vat, 2)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE orders SET total_cost = ?, total_with_vat = ? WHERE id = ?",
                   (total_cost, total_with_vat, order_id))
    conn.commit(); conn.close()
    return total_cost, total_with_vat

def set_order_status(order_id, status):
    conn = get_connection(); cursor = conn.cursor()
    if status == 'printed':
        cursor.execute("UPDATE orders SET status = ?, printed_at = ? WHERE id = ?",
                       (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), order_id))
    else:
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit(); conn.close()


def mark_order_delivery(order_id, status, error=None):
    """Фиксирует доставку заявки мастеру: pending / delivered / failed."""
    if status not in ('pending', 'delivered', 'failed'):
        raise ValueError(f"Недопустимый статус доставки: {status}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_text = (str(error)[:1000] if error else None)
    delivered_at = now if status == 'delivered' else None
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders
           SET delivery_status = ?, delivery_error = ?, delivered_at = ?
           WHERE id = ?""",
        (status, error_text, delivered_at, int(order_id)),
    )
    changed = cursor.rowcount
    conn.commit(); conn.close()
    if changed:
        log_order_event(order_id, None, f'delivery_{status}', {
            'error': error_text or '',
        })
    return bool(changed)


def get_undelivered_orders(limit=30):
    """Заявки, которые ещё не доставлены мастеру (pending/failed)."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM orders
           WHERE deleted_at IS NULL
             AND COALESCE(delivery_status, 'unknown') IN ('pending', 'failed')
           ORDER BY id DESC LIMIT ?""",
        (int(limit),),
    )
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_delivery_counts():
    """Количество заявок по статусам доставки."""
    conn = get_connection(); cursor = conn.cursor()
    rows = cursor.execute(
        """SELECT COALESCE(delivery_status, 'unknown') AS status,
                  COUNT(*) AS count
           FROM orders WHERE deleted_at IS NULL
           GROUP BY COALESCE(delivery_status, 'unknown')"""
    ).fetchall()
    conn.close()
    return {row['status']: int(row['count']) for row in rows}

def delete_order(order_id):
    """Жёсткое удаление. Для обычных действий используйте soft_delete_order."""
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit(); conn.close()


# ---------- РУЧНЫЕ НАКЛАДНЫЕ РЕЕСТРА ----------
def _batch_print_event_ids(conn, batch_id):
    """Возвращает id заявок → id первого события печати в этой пачке."""
    result = {}
    for event in conn.execute(
        """SELECT id, order_id, details FROM order_events
           WHERE action = 'printed' AND order_id IS NOT NULL
           ORDER BY id ASC"""
    ):
        order_id = int(event["order_id"])
        if order_id in result:
            continue
        try:
            details = json.loads(event["details"]) if event["details"] else {}
        except (TypeError, ValueError):
            details = {}
        try:
            event_batch = int(details.get("batch_id"))
        except (TypeError, ValueError):
            continue
        if event_batch == int(batch_id):
            result[order_id] = int(event["id"])
    return result


def _rebalance_orders_in_conn(conn, batch_id, full=False):
    """Перестраивает заявки вокруг ручных накладных.

    Ручные накладные и строки удалённых заявок считаются занятыми и не
    меняются. Заявки всегда идут в порядке фактической печати.

    full=False — двигаются только заявки в зоне конфликта и ниже, поэтому
    добавление ручной накладной не трогает записи выше.
    full=True — вся пачка пересобирается в порядке печати; это нужно для
    исправления уже перемешанного реестра.

    Транзакцией управляет вызывающий код.
    """
    batch_id = int(batch_id)
    batch = conn.execute(
        "SELECT * FROM batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if not batch:
        raise ValueError("Пачка не найдена")
    start_number = str(batch["start_number"]).strip()

    manual = conn.execute(
        """SELECT id, ttn_number, target_row FROM manual_registry
           WHERE batch_id = ?
           ORDER BY target_row DESC, id ASC""",
        (batch_id,),
    ).fetchall()
    manual_rows = set()
    manual_ttns = set()
    for entry in manual:
        ttn = str(entry["ttn_number"] or "").strip()
        if ttn:
            manual_ttns.add(ttn)
        if entry["target_row"] is not None:
            row = int(entry["target_row"])
            if not 1 <= row <= BATCH_SIZE:
                raise ValueError(
                    f"Ручная накладная №{ttn} имеет строку {row} вне 1–25")
            manual_rows.add(row)

    all_orders = conn.execute(
        """SELECT id, ttn_number, order_row, deleted_at, printed_at
           FROM orders
           WHERE batch_id = ? AND order_row IS NOT NULL
             AND ttn_number IS NOT NULL""",
        (batch_id,),
    ).fetchall()

    blocked_rows = set(manual_rows)
    blocked_ttns = set(manual_ttns)
    active_orders = []
    for order in all_orders:
        if order["deleted_at"]:
            blocked_rows.add(int(order["order_row"]))
            blocked_ttns.add(str(order["ttn_number"]).strip())
        else:
            active_orders.append(order)

    print_event_ids = _batch_print_event_ids(conn, batch_id)

    def sequence_key(order):
        order_id = int(order["id"])
        event_id = print_event_ids.get(order_id)
        if event_id is not None:
            # Событие печати — самый надёжный порядок, особенно когда
            # вся пачка подтверждена в одну секунду.
            return (0, event_id, "", order_id)
        return (1, 0, str(order["printed_at"] or ""), order_id)

    active_orders.sort(key=sequence_key)

    if full:
        cutoff = BATCH_SIZE
        to_reflow = list(active_orders)
    else:
        seen_rows = set()
        seen_ttns = set()
        conflict_rows = []
        for order in active_orders:
            row = int(order["order_row"])
            ttn = str(order["ttn_number"] or "").strip()
            if (row in blocked_rows or ttn in blocked_ttns
                    or row in seen_rows or ttn in seen_ttns):
                conflict_rows.append(row)
            seen_rows.add(row)
            seen_ttns.add(ttn)
        if not conflict_rows:
            return [], manual_rows
        cutoff = max(conflict_rows)
        to_reflow = [
            order for order in active_orders
            if int(order["order_row"]) <= cutoff
        ]

    free_rows = [
        row for row in range(cutoff, 0, -1)
        if row not in blocked_rows
    ]
    if len(free_rows) < len(to_reflow):
        raise ValueError(
            "В пачке недостаточно свободных строк для перестройки")

    moves = []
    for index, order in enumerate(to_reflow):
        new_row = free_rows[index]
        new_ttn = compute_ttn_number(
            start_number, -(BATCH_SIZE - new_row))
        old_row = int(order["order_row"])
        old_ttn = str(order["ttn_number"] or "").strip()
        if old_row == new_row and old_ttn == new_ttn:
            continue
        moves.append({
            "order_id": int(order["id"]),
            "old_row": old_row,
            "old_ttn": old_ttn,
            "new_row": new_row,
            "new_ttn": new_ttn,
        })
        conn.execute(
            "UPDATE orders SET order_row = ?, ttn_number = ? WHERE id = ?",
            (new_row, new_ttn, int(order["id"])),
        )
    return moves, manual_rows


def add_manual_registry(master_id, batch_id, entry, with_details=False):
    """Добавляет ручную накладную; заявки в зоне конфликта сдвигаются.

    Ручная накладная имеет приоритет перед заявками: если её строка или
    ТТН уже заняты активной заявкой, заявки в этой зоне сдвигаются ниже
    с сохранением порядка печати и получают новые ТТН. Конфликт двух
    ручных накладных и строки удалённых заявок по-прежнему запрещены.
    """
    master_id = int(master_id)
    batch_id = int(batch_id)
    ttn_number = str(entry.get('ttn_number', '')).strip()
    target_row = entry.get('target_row')
    if not ttn_number:
        raise ValueError("Не указан номер ТТН")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ? AND master_id = ?",
            (batch_id, master_id),
        ).fetchone()
        if not batch:
            raise ValueError("Пачка не найдена")
        if batch["closed_at"]:
            raise ValueError("Пачка уже закрыта")

        if target_row is not None:
            target_row = int(target_row)
            if not 1 <= target_row <= BATCH_SIZE:
                raise ValueError("Строка реестра вне диапазона 1–25")

            expected_ttn = compute_ttn_number(
                batch["start_number"], -(BATCH_SIZE - target_row))
            if (ttn_number.isdigit()
                    and str(batch["start_number"]).strip().isdigit()):
                if int(ttn_number) != int(expected_ttn):
                    raise ValueError(
                        f"ТТН №{ttn_number} не соответствует строке "
                        f"{target_row} (ожидается {expected_ttn})")
                ttn_number = expected_ttn

            if conn.execute(
                """SELECT 1 FROM manual_registry
                   WHERE batch_id = ? AND target_row = ?""",
                (batch_id, target_row),
            ).fetchone():
                raise ValueError(
                    f"Строка {target_row} уже занята ручной накладной")
            if conn.execute(
                """SELECT 1 FROM orders
                   WHERE batch_id = ? AND order_row = ?
                     AND deleted_at IS NOT NULL""",
                (batch_id, target_row),
            ).fetchone():
                raise ValueError(
                    f"Строка {target_row} занята удалённой заявкой")
        else:
            target_row = None

        if conn.execute(
            """SELECT 1 FROM manual_registry
               WHERE batch_id = ? AND ttn_number = ?""",
            (batch_id, ttn_number),
        ).fetchone():
            raise ValueError(
                f"ТТН №{ttn_number} уже добавлен ручной накладной")
        if conn.execute(
            """SELECT 1 FROM orders
               WHERE batch_id = ? AND ttn_number = ?
                 AND deleted_at IS NOT NULL""",
            (batch_id, ttn_number),
        ).fetchone():
            raise ValueError(
                f"ТТН №{ttn_number} занят удалённой заявкой")

        cursor = conn.execute(
            """INSERT INTO manual_registry
               (master_id, batch_id, ttn_number, date, loading_point,
                driver_name, car_plate, target_row, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (master_id, batch_id, ttn_number,
             entry.get('date', ''), entry.get('loading_point', ''),
             entry.get('driver_name', ''), entry.get('car_plate', ''),
             target_row,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        entry_id = cursor.lastrowid
        moves, _ = _rebalance_orders_in_conn(conn, batch_id)
        _recalc_counter(conn, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log_order_event(None, master_id, 'manual_registry_added', {
        'batch_id': batch_id,
        'ttn_number': ttn_number,
        'target_row': target_row,
    })
    if moves:
        log_order_event(None, master_id, 'batch_rebalanced', {
            'batch_id': batch_id,
            'reason': 'manual_registry_added',
            'manual_ttn': ttn_number,
            'manual_row': target_row,
            'moves': moves,
        })
        logger.info(
            f"🔄 Пачка {batch_id}: ручная накладная №{ttn_number} "
            f"перестроила заявки — {len(moves)}")
    if with_details:
        return {
            'entry_id': entry_id,
            'ttn_number': ttn_number,
            'target_row': target_row,
            'moves': moves,
        }
    return entry_id


def get_manual_registry(master_id, batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM manual_registry
           WHERE master_id = ? AND batch_id = ?
           ORDER BY id ASC""",
        (int(master_id), int(batch_id)),
    )
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def delete_manual_registry(entry_id, master_id=None):
    entry_id = int(entry_id)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if master_id is None:
            row = conn.execute(
                "SELECT batch_id FROM manual_registry WHERE id = ?",
                (entry_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT batch_id FROM manual_registry
                   WHERE id = ? AND master_id = ?""",
                (entry_id, int(master_id)),
            ).fetchone()
        if not row:
            conn.rollback()
            return False

        conn.execute("DELETE FROM manual_registry WHERE id = ?", (entry_id,))
        _recalc_counter(conn, int(row["batch_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if master_id is not None:
        log_order_event(None, master_id, 'manual_registry_deleted',
                        {'entry_id': entry_id})
    return True


def clear_manual_registry(master_id, batch_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "DELETE FROM manual_registry WHERE master_id = ? AND batch_id = ?",
            (int(master_id), int(batch_id)),
        )
        changed = cursor.rowcount
        _recalc_counter(conn, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    if changed:
        log_order_event(None, master_id, 'manual_registry_cleared',
                        {'batch_id': batch_id, 'count': changed})
    return changed


# ---------- ЗАНЯТЫЕ СТРОКИ ПАЧКИ ----------
def _occupied_rows(conn, batch_id, master_id=None):
    """Строки пачки, занятые заявками и ручными накладными.

    Удалённые заявки тоже считаются занятыми: их ТТН уже мог быть
    напечатан, поэтому строку нельзя отдавать другой заявке.
    """
    rows = set()
    for row in conn.execute(
        """SELECT order_row FROM orders
           WHERE batch_id = ? AND ttn_number IS NOT NULL
             AND order_row IS NOT NULL""",
        (int(batch_id),),
    ):
        if row[0] is not None:
            rows.add(int(row[0]))

    if master_id is None:
        batch = conn.execute(
            "SELECT master_id FROM batches WHERE id = ?", (int(batch_id),)
        ).fetchone()
        master_id = int(batch[0]) if batch else None

    if master_id is not None:
        for row in conn.execute(
            """SELECT target_row FROM manual_registry
               WHERE batch_id = ? AND master_id = ?
                 AND target_row IS NOT NULL""",
            (int(batch_id), int(master_id)),
        ):
            if row[0] is not None:
                rows.add(int(row[0]))

    return {row for row in rows if 1 <= row <= BATCH_SIZE}


def get_occupied_rows(batch_id, master_id=None):
    """Публичная обёртка: какие строки реестра уже заняты."""
    conn = get_connection()
    try:
        return _occupied_rows(conn, batch_id, master_id)
    finally:
        conn.close()


def get_free_rows(batch_id, master_id=None):
    """Свободные строки пачки сверху вниз: 25, 24, ..."""
    occupied = get_occupied_rows(batch_id, master_id)
    return [row for row in range(BATCH_SIZE, 0, -1) if row not in occupied]


def _recalc_counter(conn, batch_id):
    """Счётчик = число фактически занятых строк (заявки + ручные)."""
    counter = len(_occupied_rows(conn, batch_id))
    conn.execute(
        "UPDATE batches SET counter = ? WHERE id = ?", (counter, int(batch_id)))
    return counter


def recalc_batch_counter(batch_id):
    conn = get_connection()
    try:
        counter = _recalc_counter(conn, batch_id)
        conn.commit()
        return counter
    finally:
        conn.close()

# ---------- ПАЧКИ ----------
def get_active_batch(master_id):
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""SELECT * FROM batches WHERE master_id = ? AND closed_at IS NULL
                      ORDER BY id DESC LIMIT 1""", (master_id,))
    row = cursor.fetchone(); conn.close()
    return dict(row) if row else None

def create_batch(master_id, start_number):
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""INSERT INTO batches (master_id, start_number, counter, started_at)
                      VALUES (?, ?, 0, ?)""",
                   (master_id, str(start_number), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    batch_id = cursor.lastrowid
    conn.commit(); conn.close()
    logger.info(f"📦 Создана пачка id={batch_id}, верхний={start_number}")
    return batch_id


def create_batch_with_manual(master_id, start_number, entry):
    """Создаёт пачку, в которой ручная накладная занимает строку 25.

    Счётчик сразу равен 1: верхняя строка занята, поэтому следующая
    печать начнётся со строки 24 и ТТН на единицу меньше.
    Возвращает (batch_id, entry_id).
    """
    master_id = int(master_id)
    start_number = str(start_number).strip()
    if not start_number:
        raise ValueError("Не указан номер верхней накладной")

    entry = dict(entry or {})
    entry.setdefault('ttn_number', start_number)
    entry.setdefault('target_row', BATCH_SIZE)

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        active = conn.execute(
            "SELECT id FROM batches WHERE master_id = ? AND closed_at IS NULL",
            (master_id,)).fetchone()
        if active:
            raise ValueError("У мастера уже есть активная пачка")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute(
            """INSERT INTO batches
               (master_id, start_number, counter, started_at)
               VALUES (?, ?, 0, ?)""",
            (master_id, start_number, now))
        batch_id = cursor.lastrowid
        cursor = conn.execute(
            """INSERT INTO manual_registry
               (master_id, batch_id, ttn_number, date, loading_point,
                driver_name, car_plate, target_row, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (master_id, int(batch_id), str(entry.get('ttn_number', '')),
             entry.get('date', ''), entry.get('loading_point', ''),
             entry.get('driver_name', ''), entry.get('car_plate', ''),
             int(entry.get('target_row') or BATCH_SIZE), now))
        entry_id = cursor.lastrowid
        _recalc_counter(conn, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log_order_event(None, master_id, 'batch_created', {
        'batch_id': batch_id, 'start_number': start_number,
        'manual_entry_id': entry_id,
    })
    log_order_event(None, master_id, 'manual_registry_added', {
        'batch_id': batch_id,
        'ttn_number': entry.get('ttn_number', ''),
        'target_row': entry.get('target_row', BATCH_SIZE),
    })
    logger.info(
        f"📦 Пачка id={batch_id} открыта с ручной накладной "
        f"ТТН №{entry.get('ttn_number')} (стр. {entry.get('target_row')})")
    return batch_id, entry_id

def increment_batch_counter(batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE batches SET counter = counter + 1 WHERE id = ?", (batch_id,))
    conn.commit()
    cursor.execute("SELECT counter FROM batches WHERE id = ?", (batch_id,))
    row = cursor.fetchone(); conn.close()
    return row['counter'] if row else 0

def close_batch(batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE batches SET closed_at = ? WHERE id = ?",
                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), batch_id))
    conn.commit(); conn.close()

def get_batch(batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM batches WHERE id = ?", (batch_id,))
    row = cursor.fetchone(); conn.close()
    return dict(row) if row else None

def get_batch_orders(batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""SELECT * FROM orders
                      WHERE batch_id = ? AND ttn_number IS NOT NULL
                        AND order_row IS NOT NULL AND deleted_at IS NULL
                      ORDER BY order_row ASC""", (batch_id,))
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]

def get_all_batches(master_id):
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM batches WHERE master_id = ? ORDER BY id DESC", (master_id,))
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]


def get_closed_batches(master_id):
    """Закрытые непустые пачки мастера для истории реестров."""
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT b.*,
                  (SELECT COUNT(*) FROM orders o
                   WHERE o.batch_id = b.id
                     AND o.ttn_number IS NOT NULL
                     AND o.order_row IS NOT NULL
                     AND o.deleted_at IS NULL) AS orders_count,
                  (SELECT COUNT(*) FROM manual_registry m
                   WHERE m.batch_id = b.id
                     AND m.master_id = b.master_id) AS manual_count
           FROM batches b
           WHERE b.master_id = ? AND b.closed_at IS NOT NULL
           ORDER BY b.id DESC""",
        (master_id,),
    )
    rows = cursor.fetchall(); conn.close()
    result = []
    for row in rows:
        batch = dict(row)
        if batch["orders_count"] + batch["manual_count"] > 0:
            result.append(batch)
    return result


def assign_orders_to_batch(batch_id, order_ids, expected_counter=None,
                           expected_rows=None):
    """Атомарно назначает номера ТТН и строки реестра нескольким заявкам.

    Свободные строки берутся сверху вниз (25, 24, ...), при этом уже занятые
    заявками и ручными накладными строки пропускаются. Если передан
    expected_rows, состав пачки должен совпасть со снимком предпросмотра.
    Если хотя бы одну заявку уже успели изменить, вся операция откатывается.
    """
    ids = [int(order_id) for order_id in order_ids]
    if not ids:
        raise ValueError("Не выбрано ни одной заявки")
    if len(set(ids)) != len(ids):
        raise ValueError("В пакете есть повторяющиеся заявки")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (int(batch_id),)
        ).fetchone()
        if not batch:
            raise ValueError("Пачка не найдена")
        if batch["closed_at"]:
            raise ValueError("Пачка уже закрыта")

        occupied = _occupied_rows(conn, batch_id, int(batch["master_id"]))
        if expected_rows is not None:
            expected = {int(row) for row in expected_rows}
            if occupied != expected:
                raise ValueError(
                    "Состав пачки изменился. Сформируйте пакет заново.")
        counter = len(occupied)
        if expected_counter is not None and counter != int(expected_counter):
            raise ValueError("Счётчик пачки изменился. Сформируйте пакет заново.")

        free_rows = [
            row for row in range(BATCH_SIZE, 0, -1) if row not in occupied
        ]
        if len(free_rows) < len(ids):
            raise ValueError("В пачке недостаточно свободных строк")

        assignments = []
        printed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for index, order_id in enumerate(ids):
            order_row = free_rows[index]
            offset = BATCH_SIZE - order_row
            ttn_number = compute_ttn_number(batch["start_number"], -offset)

            order = conn.execute(
                """SELECT id, master_id, status, ttn_number, deleted_at
                   FROM orders WHERE id = ?""",
                (order_id,),
            ).fetchone()
            if not order:
                raise ValueError(f"Заявка №{order_id} не найдена")
            if int(order["master_id"]) != int(batch["master_id"]):
                access = conn.execute(
                    "SELECT 1 FROM order_access "
                    "WHERE order_id = ? AND master_id = ?",
                    (order_id, int(batch["master_id"])),
                ).fetchone()
                if not access:
                    raise ValueError(
                        f"Заявка №{order_id} принадлежит другому мастеру")
            if order["deleted_at"]:
                raise ValueError(f"Заявка №{order_id} удалена")
            if order["status"] not in ("new", "confirmed") or order["ttn_number"]:
                raise ValueError(f"Заявка №{order_id} уже распечатана или изменена")

            cursor = conn.execute(
                """UPDATE orders
                   SET ttn_number = ?, batch_id = ?, order_row = ?,
                       status = 'printed', printed_at = ?
                   WHERE id = ?
                     AND deleted_at IS NULL
                     AND status IN ('new', 'confirmed')
                     AND (ttn_number IS NULL OR ttn_number = '')""",
                (ttn_number, int(batch_id), order_row, printed_at,
                 order_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Заявка №{order_id} уже изменилась")

            assignments.append({
                "order_id": order_id,
                "ttn_number": ttn_number,
                "order_row": order_row,
                "batch_id": int(batch_id),
            })

        conn.execute(
            "UPDATE batches SET counter = ? WHERE id = ?",
            (counter + len(ids), int(batch_id)),
        )
        conn.commit()
        return assignments
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_order_ttn(order_id, ttn_number, batch_id, order_row=None):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE orders SET ttn_number = ?, batch_id = ?, order_row = ? WHERE id = ?",
                   (str(ttn_number), batch_id, order_row, order_id))
    conn.commit(); conn.close()

def unassign_order_from_batch(order_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT batch_id FROM orders WHERE id = ?", (int(order_id),)
        ).fetchone()
        batch_id = int(row["batch_id"]) if row and row["batch_id"] is not None else None
        conn.execute("""UPDATE orders
                        SET ttn_number = NULL, batch_id = NULL, order_row = NULL,
                            status = 'new', printed_at = NULL
                        WHERE id = ?""", (int(order_id),))
        if batch_id is not None:
            _recalc_counter(conn, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def recalc_batch_ttn(batch_id, new_start_number):
    """Пересчитывает ТТН заявок и ручных накладных, сохраняя их строки."""
    batch_id = int(batch_id)
    new_start_number = str(new_start_number).strip()
    if not new_start_number:
        raise ValueError("Не указан номер верхней накладной")

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute(
            "SELECT id FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise ValueError("Пачка не найдена")

        for row in conn.execute(
            """SELECT id, order_row FROM orders
               WHERE batch_id = ? AND order_row IS NOT NULL
                 AND ttn_number IS NOT NULL""",
            (batch_id,),
        ):
            offset = BATCH_SIZE - int(row["order_row"])
            ttn = compute_ttn_number(new_start_number, -offset)
            conn.execute(
                "UPDATE orders SET ttn_number = ? WHERE id = ?",
                (ttn, row["id"]))

        for row in conn.execute(
            """SELECT id, target_row FROM manual_registry
               WHERE batch_id = ? AND target_row IS NOT NULL""",
            (batch_id,),
        ):
            offset = BATCH_SIZE - int(row["target_row"])
            ttn = compute_ttn_number(new_start_number, -offset)
            conn.execute(
                "UPDATE manual_registry SET ttn_number = ? WHERE id = ?",
                (ttn, row["id"]))

        counter = _recalc_counter(conn, batch_id)
        conn.execute(
            "UPDATE batches SET start_number = ? WHERE id = ?",
            (new_start_number, batch_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info(
        f"🔁 Пачка {batch_id}: ТТН пересчитаны от {new_start_number} "
        f"(занято строк: {counter})")

def repair_batch_layout(batch_id, dry_run=False):
    """Пересобирает пачку в порядке фактической печати.

    Ручные накладные считаются приоритетными: их строки и номера не
    меняются. Заявки выстраиваются в порядке событий печати и получают
    свободные строки сверху вниз с пересчётом ТТН. Пустые строки от
    удалённых заявок остаются зарезервированными.
    """
    batch_id = int(batch_id)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        batch = conn.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise ValueError("Пачка не найдена")

        moves, manual_rows = _rebalance_orders_in_conn(
            conn, batch_id, full=True)
        if dry_run:
            conn.rollback()
        else:
            _recalc_counter(conn, batch_id)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if moves and not dry_run:
        log_order_event(None, batch["master_id"], 'batch_repaired', {
            'batch_id': batch_id,
            'moves': moves,
        })
        logger.info(
            f"🛠 Пачка {batch_id}: перестроено заявок — {len(moves)}")

    return {
        "batch_id": batch_id,
        "dry_run": bool(dry_run),
        "manual_rows": sorted(manual_rows, reverse=True),
        "moves": moves,
    }


def reset_batch(batch_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""UPDATE orders
                        SET ttn_number = NULL, batch_id = NULL, order_row = NULL,
                            status = 'new', printed_at = NULL
                        WHERE batch_id = ? AND deleted_at IS NULL""", (int(batch_id),))
        _recalc_counter(conn, batch_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info(f"🔄 Пачка {batch_id} сброшена")

def compute_ttn_number(start_number, offset):
    s = str(start_number).strip()
    if not s: return str(abs(offset) + 1)
    width = len(s)
    try:
        n = int(s) + offset
        return str(n).zfill(width)
    except ValueError:
        return s

init_db()
logger.info("✅ orders_db инициализирован")
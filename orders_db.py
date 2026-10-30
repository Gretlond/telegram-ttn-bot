# =============================================================
# РАБОТА С БАЗОЙ ДАННЫХ ЗАЯВОК (SQLite)
# =============================================================
import sqlite3
import json
import os
from datetime import datetime

DB_FILE = "orders.db"
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_order ON order_events(order_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_batch ON manual_registry(master_id, batch_id)")
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
            print(f"➕ Миграция: orders.{col}")
            try: cursor.execute(sql); conn.commit()
            except Exception as e: print(f"⚠️ {e}")

    # WAL уменьшает блокировки при одновременной работе водителей и мастеров.
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        print(f"⚠️ Не удалось включить WAL: {e}")
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
        print(f"⚠️ Не удалось записать событие аудита: {e}")


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
    print(f"✅ Заявка сохранена: order_id={order_id}")
    return order_id

def get_order(order_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = cursor.fetchone(); conn.close()
    return dict(row) if row else None

def get_master_orders(master_id, status=None):
    master_id = int(master_id)
    conn = get_connection(); cursor = conn.cursor()
    if status:
        cursor.execute(
            """SELECT * FROM orders
               WHERE master_id = ? AND status = ? AND deleted_at IS NULL
               ORDER BY id DESC""",
            (master_id, status))
    else:
        cursor.execute(
            """SELECT * FROM orders
               WHERE master_id = ? AND deleted_at IS NULL
               ORDER BY id DESC""",
            (master_id,))
    rows = cursor.fetchall(); conn.close()
    return [dict(r) for r in rows]

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
        print(f"Недопустимое поле: {field}"); return
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
        try:
            qty = float(str(c.get('cargo_qty','0')).replace(',', '.'))
            price = float(str(c.get('price','0')).replace(',', '.'))
        except (ValueError, TypeError):
            continue
        cost = qty * price
        vat = cost * 0.20 if c.get('vat_rate') == '20%' else 0.0
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
def add_manual_registry(master_id, batch_id, entry):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO manual_registry
           (master_id, batch_id, ttn_number, date, loading_point,
            driver_name, car_plate, target_row, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (int(master_id), int(batch_id), str(entry.get('ttn_number', '')),
         entry.get('date', ''), entry.get('loading_point', ''),
         entry.get('driver_name', ''), entry.get('car_plate', ''),
         entry.get('target_row'),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    entry_id = cursor.lastrowid
    conn.commit(); conn.close()
    log_order_event(None, master_id, 'manual_registry_added', {
        'batch_id': batch_id,
        'ttn_number': entry.get('ttn_number', ''),
        'target_row': entry.get('target_row'),
    })
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
    conn = get_connection(); cursor = conn.cursor()
    if master_id is None:
        cursor.execute("DELETE FROM manual_registry WHERE id = ?", (int(entry_id),))
    else:
        cursor.execute(
            "DELETE FROM manual_registry WHERE id = ? AND master_id = ?",
            (int(entry_id), int(master_id)),
        )
    changed = cursor.rowcount
    conn.commit(); conn.close()
    if changed and master_id is not None:
        log_order_event(None, master_id, 'manual_registry_deleted',
                        {'entry_id': entry_id})
    return bool(changed)


def clear_manual_registry(master_id, batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM manual_registry WHERE master_id = ? AND batch_id = ?",
        (int(master_id), int(batch_id)),
    )
    changed = cursor.rowcount
    conn.commit(); conn.close()
    if changed:
        log_order_event(None, master_id, 'manual_registry_cleared',
                        {'batch_id': batch_id, 'count': changed})
    return changed

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
    print(f"📦 Создана пачка id={batch_id}, верхний={start_number}")
    return batch_id

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


def assign_orders_to_batch(batch_id, order_ids, expected_counter=None):
    """Атомарно назначает номера ТТН и строки реестра нескольким заявкам.

    Номера идут вниз от номера сверху пачки, строки реестра — с конца (25, 24...).
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

        counter = int(batch["counter"] or 0)
        if expected_counter is not None and counter != int(expected_counter):
            raise ValueError("Счётчик пачки изменился. Сформируйте пакет заново.")
        if counter + len(ids) > BATCH_SIZE:
            raise ValueError("В пачке недостаточно свободных строк")

        assignments = []
        printed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for index, order_id in enumerate(ids):
            offset = counter + index
            order_row = BATCH_SIZE - offset
            ttn_number = compute_ttn_number(batch["start_number"], -offset)

            order = conn.execute(
                """SELECT id, master_id, status, ttn_number, deleted_at
                   FROM orders WHERE id = ?""",
                (order_id,),
            ).fetchone()
            if not order:
                raise ValueError(f"Заявка №{order_id} не найдена")
            if int(order["master_id"]) != int(batch["master_id"]):
                raise ValueError(f"Заявка №{order_id} принадлежит другому мастеру")
            if order["deleted_at"]:
                raise ValueError(f"Заявка №{order_id} удалена")
            if order["status"] not in ("new", "confirmed") or order["ttn_number"]:
                raise ValueError(f"Заявка №{order_id} уже распечатана или изменена")

            cursor = conn.execute(
                """UPDATE orders
                   SET ttn_number = ?, batch_id = ?, order_row = ?,
                       status = 'printed', printed_at = ?
                   WHERE id = ? AND master_id = ?
                     AND deleted_at IS NULL
                     AND status IN ('new', 'confirmed')
                     AND (ttn_number IS NULL OR ttn_number = '')""",
                (ttn_number, int(batch_id), order_row, printed_at,
                 order_id, int(batch["master_id"])),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Заявка №{order_id} уже изменилась")

            assignments.append({
                "order_id": order_id,
                "ttn_number": ttn_number,
                "order_row": order_row,
                "batch_id": int(batch_id),
            })

        cursor = conn.execute(
            "UPDATE batches SET counter = counter + ? WHERE id = ? AND counter = ?",
            (len(ids), int(batch_id), counter),
        )
        if cursor.rowcount != 1:
            raise ValueError("Не удалось обновить счётчик пачки")
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
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""UPDATE orders
                      SET ttn_number = NULL, batch_id = NULL, order_row = NULL,
                          status = 'new', printed_at = NULL
                      WHERE id = ?""", (order_id,))
    conn.commit(); conn.close()

def recalc_batch_ttn(batch_id, new_start_number):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute(
        """SELECT id FROM orders
           WHERE batch_id = ? AND deleted_at IS NULL
           ORDER BY id ASC""",
        (batch_id,))
    rows = cursor.fetchall()
    for idx, row in enumerate(rows):
        order_row = BATCH_SIZE - idx
        ttn = compute_ttn_number(new_start_number, -idx)
        cursor.execute("UPDATE orders SET ttn_number = ?, order_row = ? WHERE id = ?",
                       (ttn, order_row, row['id']))
    cursor.execute("UPDATE batches SET start_number = ? WHERE id = ?",
                   (str(new_start_number), batch_id))
    conn.commit(); conn.close()
    print(f"🔁 Пачка {batch_id}: ТТН пересчитаны от {new_start_number}")

def reset_batch(batch_id):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""UPDATE orders
                      SET ttn_number = NULL, batch_id = NULL, order_row = NULL,
                          status = 'new', printed_at = NULL
                      WHERE batch_id = ? AND deleted_at IS NULL""", (batch_id,))
    cursor.execute("UPDATE batches SET counter = 0 WHERE id = ?", (batch_id,))
    conn.commit(); conn.close()
    print(f"🔄 Пачка {batch_id} сброшена")

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
print("✅ orders_db инициализирован")
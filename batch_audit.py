# =============================================================
# АУДИТ ЦЕЛОСТНОСТИ ПАЧЕК РЕЕСТРА
# =============================================================
"""Проверяет пачки на дубли строк и ТТН, конфликты с ручными
накладными, расхождения счётчика и осиротевшие ссылки.

Модуль только читает базу. Запуск вручную:

    python batch_audit.py
    python batch_audit.py --db /path/to/orders.db --json
"""
import argparse
import json
import os
import sys

import orders_db


def _issue(batch_id, code, message):
    return {
        "batch_id": batch_id,
        "code": code,
        "message": message,
    }


def _label_order(order):
    suffix = " (удалена)" if order["deleted_at"] else ""
    return f"заявка №{order['id']}{suffix}"


def _label_manual(entry):
    return f"ручная №{entry['id']}"


def _audit_rows_and_ttns(batch_id, orders, manual, issues):
    row_owners = {}
    ttn_owners = {}

    for order in orders:
        row = order["order_row"]
        ttn = str(order["ttn_number"] or "").strip()
        if row is not None:
            row_owners.setdefault(int(row), []).append(_label_order(order))
        if ttn:
            ttn_owners.setdefault(ttn, []).append(_label_order(order))

    for entry in manual:
        row = entry["target_row"]
        ttn = str(entry["ttn_number"] or "").strip()
        if row is not None:
            row_owners.setdefault(int(row), []).append(_label_manual(entry))
        if ttn:
            ttn_owners.setdefault(ttn, []).append(_label_manual(entry))

    for row, owners in sorted(row_owners.items()):
        if len(owners) > 1:
            issues.append(_issue(
                batch_id, "duplicate_row",
                f"строка {row} занята несколько раз: {', '.join(owners)}"))

    for ttn, owners in sorted(ttn_owners.items()):
        if len(owners) > 1:
            issues.append(_issue(
                batch_id, "duplicate_ttn",
                f"ТТН {ttn} встречается несколько раз: {', '.join(owners)}"))


def _audit_entries(batch_id, orders, manual, issues):
    for order in orders:
        row = order["order_row"]
        ttn = str(order["ttn_number"] or "").strip()
        if row is None and ttn:
            issues.append(_issue(
                batch_id, "order_missing_row",
                f"заявка №{order['id']} имеет ТТН {ttn}, но не имеет строки"))
        elif row is not None and not ttn:
            issues.append(_issue(
                batch_id, "order_missing_ttn",
                f"заявка №{order['id']} занимает строку {row}, но не имеет ТТН"))
        if row is not None and not 1 <= int(row) <= orders_db.BATCH_SIZE:
            issues.append(_issue(
                batch_id, "row_out_of_range",
                f"заявка №{order['id']} имеет строку {row} вне 1–25"))

    for entry in manual:
        row = entry["target_row"]
        ttn = str(entry["ttn_number"] or "").strip()
        if not ttn:
            issues.append(_issue(
                batch_id, "manual_missing_ttn",
                f"ручная накладная №{entry['id']} без номера ТТН"))
        if row is None:
            issues.append(_issue(
                batch_id, "manual_missing_row",
                f"ручная накладная №{entry['id']} не имеет строки"))
        elif not 1 <= int(row) <= orders_db.BATCH_SIZE:
            issues.append(_issue(
                batch_id, "row_out_of_range",
                f"ручная накладная №{entry['id']} имеет строку {row} "
                "вне 1–25"))


def _audit_batch(conn, batch, issues):
    batch_id = int(batch["id"])
    orders = conn.execute(
        """SELECT id, order_row, ttn_number, deleted_at
           FROM orders
           WHERE batch_id = ? AND (order_row IS NOT NULL
                                   OR (ttn_number IS NOT NULL
                                       AND TRIM(ttn_number) <> ''))""",
        (batch_id,),
    ).fetchall()
    manual = conn.execute(
        """SELECT id, master_id, target_row, ttn_number
           FROM manual_registry WHERE batch_id = ?""",
        (batch_id,),
    ).fetchall()

    _audit_entries(batch_id, orders, manual, issues)
    _audit_rows_and_ttns(batch_id, orders, manual, issues)

    for entry in manual:
        if int(entry["master_id"]) != int(batch["master_id"]):
            issues.append(_issue(
                batch_id, "manual_master_mismatch",
                f"ручная накладная №{entry['id']} принадлежит мастеру "
                f"{entry['master_id']}, а пачка — {batch['master_id']}"))

    occupied = {
        int(order["order_row"]) for order in orders
        if order["order_row"] is not None
        and 1 <= int(order["order_row"]) <= orders_db.BATCH_SIZE
    }
    occupied.update(
        int(entry["target_row"]) for entry in manual
        if entry["target_row"] is not None
        and 1 <= int(entry["target_row"]) <= orders_db.BATCH_SIZE
    )
    if int(batch["counter"] or 0) != len(occupied):
        issues.append(_issue(
            batch_id, "counter_mismatch",
            f"счётчик {batch['counter']} не совпадает с занятыми "
            f"строками ({len(occupied)})"))

    active = sum(1 for order in orders if not order["deleted_at"])
    deleted = len(orders) - active
    return {
        "id": batch_id,
        "master_id": int(batch["master_id"]),
        "closed": batch["closed_at"] is not None,
        "counter": int(batch["counter"] or 0),
        "occupied": len(occupied),
        "manual": len(manual),
        "active_orders": active,
        "deleted_orders": deleted,
        "issues": sum(1 for issue in issues if issue["batch_id"] == batch_id),
    }


def _audit_orphans(conn, issues):
    for row in conn.execute(
        """SELECT batch_id, COUNT(*) AS amount FROM orders
           WHERE batch_id IS NOT NULL
             AND batch_id NOT IN (SELECT id FROM batches)
           GROUP BY batch_id"""
    ):
        issues.append(_issue(
            None, "orphan_order_batch",
            f"заявки ссылаются на несуществующую пачку "
            f"№{row['batch_id']} ({row['amount']} шт.)"))

    for row in conn.execute(
        """SELECT batch_id, COUNT(*) AS amount FROM manual_registry
           WHERE batch_id IS NOT NULL
             AND batch_id NOT IN (SELECT id FROM batches)
           GROUP BY batch_id"""
    ):
        issues.append(_issue(
            None, "orphan_manual_batch",
            f"ручные накладные ссылаются на несуществующую пачку "
            f"№{row['batch_id']} ({row['amount']} шт.)"))


def _audit_global_ttns(conn, issues):
    rows = conn.execute(
        """SELECT ttn_number,
                  GROUP_CONCAT(DISTINCT batch_key) AS batches,
                  COUNT(*) AS amount
           FROM (
               SELECT TRIM(ttn_number) AS ttn_number,
                      COALESCE(CAST(batch_id AS TEXT), '—') AS batch_key
               FROM orders
               WHERE ttn_number IS NOT NULL AND TRIM(ttn_number) <> ''
               UNION ALL
               SELECT TRIM(ttn_number) AS ttn_number,
                      COALESCE(CAST(batch_id AS TEXT), '—') AS batch_key
               FROM manual_registry
               WHERE ttn_number IS NOT NULL AND TRIM(ttn_number) <> ''
           )
           GROUP BY ttn_number
           HAVING amount > 1"""
    ).fetchall()
    for row in rows:
        batches = [item for item in str(row["batches"]).split(",") if item]
        if len(set(batches)) <= 1 and "—" not in batches:
            continue
        issues.append(_issue(
            None, "global_duplicate_ttn",
            f"ТТН {row['ttn_number']} встречается в разных пачках: "
            f"{', '.join(batches)}"))


def audit_batches(conn=None):
    """Возвращает результат аудита всех пачек.

    Результат: {"ok": bool, "issues": [...], "summaries": [...]}.
    """
    own_connection = conn is None
    if own_connection:
        conn = orders_db.get_connection()
    try:
        issues = []
        summaries = []
        batches = conn.execute(
            "SELECT * FROM batches ORDER BY id").fetchall()
        for batch in batches:
            summaries.append(_audit_batch(conn, batch, issues))
        _audit_orphans(conn, issues)
        _audit_global_ttns(conn, issues)
        return {
            "ok": not issues,
            "issues": issues,
            "summaries": summaries,
        }
    finally:
        if own_connection:
            conn.close()


def format_report(result, max_issues=50):
    lines = []
    total = len(result["summaries"])
    if result["ok"]:
        lines.append(
            f"✅ Аудит пачек: проверено {total}, ошибок нет.")
        return "\n".join(lines)

    lines.append(
        f"⚠️ Аудит пачек: проверено {total}, "
        f"найдено проблем — {len(result['issues'])}.")
    shown = 0
    for issue in result["issues"]:
        if shown >= max_issues:
            lines.append(f"… и ещё {len(result['issues']) - shown}")
            break
        prefix = f"Пачка №{issue['batch_id']}: " if issue["batch_id"] else ""
        lines.append(f"• {prefix}{issue['message']}")
        shown += 1
    return "\n".join(lines)


def format_health_summary(result, max_issues=3):
    total = len(result["summaries"])
    if result["ok"]:
        return f"Целостность пачек: ✅ проверено {total}, ошибок нет"
    lines = [
        f"Целостность пачек: ⚠️ проблем — {len(result['issues'])}"
    ]
    for issue in result["issues"][:max_issues]:
        prefix = f"№{issue['batch_id']}: " if issue["batch_id"] else ""
        lines.append(f"  • {prefix}{issue['message']}")
    if len(result["issues"]) > max_issues:
        lines.append(f"  • … и ещё {len(result['issues']) - max_issues}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Проверить целостность пачек реестра")
    parser.add_argument("--db", default=None, help="путь к orders.db")
    parser.add_argument("--json", action="store_true",
                        help="вывести результат в JSON")
    args = parser.parse_args(argv)

    os.environ.setdefault("TTN_LOG_TO_FILE", "0")
    if args.db:
        orders_db.DB_FILE = os.path.abspath(args.db)

    try:
        result = audit_batches()
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

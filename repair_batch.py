#!/usr/bin/env python3
# =============================================================
# ИСПРАВЛЕНИЕ НАЛОЖЕНИЙ В ПАЧКЕ
# =============================================================
"""Пересобирает заявки пачки в порядке фактической печати.

По умолчанию работает как предпросмотр. Для изменения базы добавьте
--apply. Ручные накладные остаются на своих строках и с прежними ТТН.
"""
import argparse
import json
import os
import sys


def _print_result(result):
    print(f"Пачка №{result['batch_id']}")
    rows = result.get("manual_rows") or []
    print(f"Ручные строки: {', '.join(map(str, rows)) or '—'}")
    moves = result.get("moves") or []
    if not moves:
        print("Пачка уже в правильном порядке.")
        return
    print(f"Переносов: {len(moves)}")
    for move in moves:
        print(
            f"  заявка №{move['order_id']}: "
            f"стр. {move['old_row']} (ТТН {move['old_ttn']}) -> "
            f"стр. {move['new_row']} (ТТН {move['new_ttn']})")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Исправить наложения заявок и ручных накладных в пачке")
    parser.add_argument("--batch", type=int, required=True, help="номер пачки")
    parser.add_argument("--db", default=None, help="путь к orders.db")
    parser.add_argument("--apply", action="store_true",
                        help="применить изменения (по умолчанию предпросмотр)")
    args = parser.parse_args(argv)

    if args.db:
        os.environ["TTN_DB_FILE"] = os.path.abspath(args.db)
    os.environ.setdefault("TTN_LOG_TO_FILE", "0")

    import orders_db

    try:
        result = orders_db.repair_batch_layout(
            args.batch, dry_run=not args.apply)
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1

    _print_result(result)
    if result["dry_run"]:
        print("\nЭто предпросмотр. Для применения добавьте --apply.")
    else:
        print("\nИзменения сохранены.")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# =============================================================
# ИСПРАВЛЕНИЕ НАЛОЖЕНИЙ В ПАЧКЕ
# =============================================================
"""Пересобирает заявки пачки в порядке фактической печати.

По умолчанию работает как предпросмотр. Для изменения базы добавьте
--apply. Ручные накладные остаются на своих строках и с прежними ТТН.
После применения к основной базе реестр DOCX/PDF перегенерируется
автоматически; для копии базы это можно включить флагом --registry.
"""
import argparse
import json
import os
import sys

import batch_registry


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


def _should_refresh_registry(args):
    if not args.apply or args.no_registry:
        return False
    if args.registry:
        return True
    # Для копии базы по умолчанию не трогаем рабочий каталог «Результат».
    return args.db is None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Исправить наложения заявок и ручных накладных в пачке")
    parser.add_argument("--batch", type=int, required=True, help="номер пачки")
    parser.add_argument("--db", default=None, help="путь к orders.db")
    parser.add_argument("--apply", action="store_true",
                        help="применить изменения (по умолчанию предпросмотр)")
    parser.add_argument("--no-registry", action="store_true",
                        help="не перегенерировать реестр после применения")
    parser.add_argument("--registry", action="store_true",
                        help="перегенерировать реестр даже для копии базы")
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
        if _should_refresh_registry(args):
            try:
                docx_path, pdf_path = batch_registry.regenerate_batch_registry(
                    args.batch)
            except Exception as e:
                print(
                    f"\nВНИМАНИЕ: реестр не перегенерирован: {e}",
                    file=sys.stderr)
            else:
                print(f"\nРеестр обновлён: {docx_path}")
                if pdf_path:
                    print(f"PDF: {pdf_path}")
        elif not args.no_registry:
            print("\nРеестр не перегенерирован: используется копия базы "
                  "(добавьте --registry).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

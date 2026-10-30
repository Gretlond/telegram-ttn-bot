import json
import sqlite3
from pathlib import Path

import backup


def test_backup_verify_and_restore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = sqlite3.connect('orders.db')
    conn.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, value TEXT)')
    conn.execute("INSERT INTO orders (value) VALUES ('live')")
    conn.commit()
    conn.close()

    Path('data').mkdir()
    Path('data/units.json').write_text(
        json.dumps({'т': 'тонна'}, ensure_ascii=False), encoding='utf-8')
    Path('masters.json').write_text('{"1": {"name": "Мастер"}}', encoding='utf-8')
    Path('last_orders.json').write_text('{}', encoding='utf-8')

    target = backup.make_backup()
    assert backup.verify_backup(target) == []

    # Меняем живую БД и восстанавливаем копию.
    conn = sqlite3.connect('orders.db')
    conn.execute("UPDATE orders SET value = 'changed'")
    conn.commit()
    conn.close()

    assert backup.restore_backup(target, assume_yes=True) is True
    conn = sqlite3.connect('orders.db')
    value = conn.execute('SELECT value FROM orders').fetchone()[0]
    conn.close()
    assert value == 'live'
    assert Path('data/units.json').exists()


def test_cleanup_keeps_only_latest_backups(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(backup, "BACKUP_DIR", "backup")
    monkeypatch.setattr(backup, "MAX_BACKUPS", 2)
    for day in ("2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"):
        (tmp_path / "backup" / day).mkdir(parents=True)

    backup.cleanup_old_backups()

    remaining = sorted(p.name for p in (tmp_path / "backup").iterdir())
    assert remaining == ["2026-10-27", "2026-10-28"]


def test_verify_rejects_broken_database(tmp_path):
    target = tmp_path / 'broken'
    target.mkdir()
    (target / 'orders.db').write_bytes(b'not a database')
    errors = backup.verify_backup(str(target))
    assert errors

import pytest

import orders_db
import repair_batch


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_repair.db"))
    orders_db.init_db()
    return orders_db


def _manual(ttn, row):
    return {
        'ttn_number': ttn, 'date': '29.10.26',
        'loading_point': 'Склад', 'driver_name': 'Петров П.П.',
        'car_plate': '7777 AB', 'target_row': row,
    }


def _batch(temp_db):
    batch_id, _ = temp_db.create_batch_with_manual(
        500, '0219200', _manual('0219200', 25))
    return batch_id


def _patch_registry(monkeypatch):
    calls = []

    def fake_regenerate(batch_id):
        calls.append(batch_id)
        return 'registry.docx', 'registry.pdf'

    monkeypatch.setattr(
        repair_batch.batch_registry,
        'regenerate_batch_registry',
        fake_regenerate,
    )
    return calls


def test_repair_cli_refreshes_registry_after_apply(
    temp_db, monkeypatch, capsys
):
    batch_id = _batch(temp_db)
    calls = _patch_registry(monkeypatch)

    code = repair_batch.main(['--batch', str(batch_id), '--apply'])

    assert code == 0
    assert calls == [batch_id]
    output = capsys.readouterr().out
    assert 'Реестр обновлён' in output
    assert 'PDF: registry.pdf' in output


def test_repair_cli_no_registry_skips_refresh(
    temp_db, monkeypatch, capsys
):
    batch_id = _batch(temp_db)
    calls = _patch_registry(monkeypatch)

    code = repair_batch.main(
        ['--batch', str(batch_id), '--apply', '--no-registry'])

    assert code == 0
    assert calls == []
    output = capsys.readouterr().out
    assert 'Реестр обновлён' not in output


def test_repair_cli_copy_db_skips_registry_by_default(
    temp_db, monkeypatch, capsys
):
    batch_id = _batch(temp_db)
    calls = _patch_registry(monkeypatch)
    monkeypatch.setenv('TTN_DB_FILE', temp_db.DB_FILE)

    code = repair_batch.main([
        '--batch', str(batch_id), '--apply', '--db', temp_db.DB_FILE])

    assert code == 0
    assert calls == []
    output = capsys.readouterr().out
    assert 'используется копия базы' in output


def test_repair_cli_registry_flag_forces_refresh_for_copy(
    temp_db, monkeypatch
):
    batch_id = _batch(temp_db)
    calls = _patch_registry(monkeypatch)
    monkeypatch.setenv('TTN_DB_FILE', temp_db.DB_FILE)

    code = repair_batch.main([
        '--batch', str(batch_id), '--apply', '--db', temp_db.DB_FILE,
        '--registry'])

    assert code == 0
    assert calls == [batch_id]


def test_repair_cli_returns_error_when_registry_fails(
    temp_db, monkeypatch, capsys
):
    batch_id = _batch(temp_db)

    def broken_regenerate(batch_id):
        raise RuntimeError('LibreOffice не найден')

    monkeypatch.setattr(
        repair_batch.batch_registry,
        'regenerate_batch_registry',
        broken_regenerate,
    )

    code = repair_batch.main(['--batch', str(batch_id), '--apply'])

    assert code == 2
    error = capsys.readouterr().err
    assert 'реестр не перегенерирован' in error
    assert 'LibreOffice не найден' in error

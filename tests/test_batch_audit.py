import pytest

import batch_audit
import batch_registry
import orders_db
import registry_filler


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_audit.db"))
    orders_db.init_db()
    return orders_db


def _order_data(number=1):
    return {
        'day': '22', 'month': '10', 'year': '26',
        'waybill_number': f'WB-{number}', 'car_model': 'МАЗ',
        'car_plate': f'1234 AB-{number}', 'trailer_info': '-',
        'loading_point': 'Склад', 'unloading_point': 'Объект',
        'driver_name': 'Иванов И.И.',
        'cargos': [{'cargo_name': 'Песок', 'cargo_qty': '10',
                    'places': '2', 'price': '100'}],
    }


def _manual(ttn, row):
    return {
        'ttn_number': ttn, 'date': '29.10.26',
        'loading_point': 'Склад', 'driver_name': 'Петров П.П.',
        'car_plate': '7777 AB', 'target_row': row,
    }


def _clean_batch(temp_db):
    batch_id, _ = temp_db.create_batch_with_manual(
        500, '0219200', _manual('0219200', 25))
    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)
    temp_db.assign_orders_to_batch(batch_id, [order_id])
    return batch_id, order_id


def test_audit_clean_batch(temp_db):
    batch_id, _ = _clean_batch(temp_db)

    result = batch_audit.audit_batches()

    assert result['ok']
    assert result['issues'] == []
    summary = result['summaries'][0]
    assert summary['id'] == batch_id
    assert summary['occupied'] == 2
    assert summary['counter'] == 2
    assert summary['manual'] == 1
    assert summary['active_orders'] == 1


def test_audit_detects_duplicate_row(temp_db):
    batch_id, order_id = _clean_batch(temp_db)
    conn = temp_db.get_connection()
    conn.execute("UPDATE orders SET order_row = 25 WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    result = batch_audit.audit_batches()

    assert not result['ok']
    assert any(
        issue['batch_id'] == batch_id and issue['code'] == 'duplicate_row'
        for issue in result['issues'])


def test_audit_detects_duplicate_ttn(temp_db):
    batch_id, order_id = _clean_batch(temp_db)
    conn = temp_db.get_connection()
    conn.execute(
        "UPDATE orders SET ttn_number = '0219200' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    result = batch_audit.audit_batches()

    assert not result['ok']
    assert any(
        issue['batch_id'] == batch_id and issue['code'] == 'duplicate_ttn'
        for issue in result['issues'])


def test_audit_detects_counter_mismatch(temp_db):
    batch_id, _ = _clean_batch(temp_db)
    conn = temp_db.get_connection()
    conn.execute("UPDATE batches SET counter = 0 WHERE id = ?", (batch_id,))
    conn.commit()
    conn.close()

    result = batch_audit.audit_batches()

    assert not result['ok']
    assert any(
        issue['batch_id'] == batch_id and issue['code'] == 'counter_mismatch'
        for issue in result['issues'])


def test_audit_detects_row_out_of_range(temp_db):
    batch_id, order_id = _clean_batch(temp_db)
    conn = temp_db.get_connection()
    conn.execute("UPDATE orders SET order_row = 26 WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    result = batch_audit.audit_batches()

    assert not result['ok']
    assert any(
        issue['batch_id'] == batch_id and issue['code'] == 'row_out_of_range'
        for issue in result['issues'])


def test_audit_report_contains_batch_and_issue(temp_db):
    batch_id, order_id = _clean_batch(temp_db)
    conn = temp_db.get_connection()
    conn.execute("UPDATE orders SET order_row = 25 WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    text = batch_audit.format_report(batch_audit.audit_batches())

    assert f"Пачка №{batch_id}" in text
    assert "строка 25 занята несколько раз" in text


def test_read_master_name_prefers_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('REGISTRY_MASTER_NAME', ' "Иванов И.И." ')

    assert batch_registry.read_master_name(
        str(tmp_path / '.env')) == 'Иванов И.И.'


def test_read_master_name_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv('REGISTRY_MASTER_NAME', raising=False)
    env_file = tmp_path / '.env'
    env_file.write_text(
        'BOT_TOKEN=test\nREGISTRY_MASTER_NAME="Рудзь Д.Ю."\n',
        encoding='utf-8')

    assert batch_registry.read_master_name(str(env_file)) == 'Рудзь Д.Ю.'


def test_regenerate_batch_registry_uses_current_data(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        orders_db, 'get_batch',
        lambda batch_id: {'id': batch_id, 'master_id': 500})
    monkeypatch.setattr(
        orders_db, 'get_batch_orders',
        lambda batch_id: [{'id': 1, 'order_row': 24}])
    monkeypatch.setattr(
        orders_db, 'get_manual_registry',
        lambda master_id, batch_id: [{'id': 2, 'target_row': 25}])

    def fake_generate(orders, master_name, output_name, manual):
        captured.update({
            'orders': orders,
            'master_name': master_name,
            'output_name': output_name,
            'manual': manual,
        })
        return 'registry.docx', None

    monkeypatch.setattr(registry_filler, 'generate_registry', fake_generate)

    result = batch_registry.regenerate_batch_registry(
        7, master_name='Мастер')

    assert result == ('registry.docx', None)
    assert captured['orders'] == [{'id': 1, 'order_row': 24}]
    assert captured['manual'] == [{'id': 2, 'target_row': 25}]
    assert captured['master_name'] == 'Мастер'
    assert captured['output_name'] == 'Реестр_ТТН_batch7_частичный'

import pytest

import orders_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_orders.db"))
    orders_db.init_db()
    return orders_db


def order_data():
    return {
        'day': '22', 'month': '10', 'year': '26',
        'waybill_number': 'WB-1', 'car_model': 'МАЗ', 'car_plate': '1234 AB',
        'trailer_info': '-', 'loading_point': 'Склад', 'unloading_point': 'Объект',
        'driver_name': 'Иванов И.И.',
        'cargos': [{'cargo_name': 'Песок', 'cargo_qty': '10',
                    'places': '2', 'price': '100'}],
    }


def test_soft_delete_and_restore_keep_history(temp_db):
    order_id = temp_db.save_order(order_data(), master_id=500, driver_id=900)
    assert temp_db.get_master_orders(500)[0]['id'] == order_id

    assert temp_db.soft_delete_order(order_id, 500, reason='test') is True
    assert temp_db.get_master_orders(500) == []
    assert temp_db.get_order(order_id)['status'] == 'deleted'
    assert temp_db.get_deleted_orders()[0]['id'] == order_id

    actions = [e['action'] for e in temp_db.get_order_events(order_id)]
    assert 'created' in actions
    assert 'deleted' in actions

    assert temp_db.restore_order(order_id, 500) is True
    assert temp_db.get_master_orders(500)[0]['id'] == order_id
    assert temp_db.get_order(order_id)['status'] == 'new'
    assert 'restored' in [e['action'] for e in temp_db.get_order_events(order_id)]


def test_manual_registry_is_persisted_and_scoped_to_batch(temp_db):
    batch_id = temp_db.create_batch(500, '0217975')
    other_batch = temp_db.create_batch(501, '0218000')
    entry_id = temp_db.add_manual_registry(500, batch_id, {
        'ttn_number': '0217975', 'date': '22.10.26',
        'loading_point': 'Склад', 'driver_name': 'Петров П.П.',
        'car_plate': '7777 AB', 'target_row': 25,
    })
    temp_db.add_manual_registry(501, other_batch, {
        'ttn_number': '0218000', 'date': '22.10.26',
        'loading_point': 'Склад', 'driver_name': 'Сидоров С.С.',
        'car_plate': '8888 AB', 'target_row': 25,
    })

    rows = temp_db.get_manual_registry(500, batch_id)
    assert len(rows) == 1
    assert rows[0]['id'] == entry_id
    assert rows[0]['ttn_number'] == '0217975'

    assert temp_db.delete_manual_registry(entry_id, 500) is True
    assert temp_db.get_manual_registry(500, batch_id) == []
    assert len(temp_db.get_manual_registry(501, other_batch)) == 1

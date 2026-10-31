import pytest

import orders_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_access.db"))
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


def test_owner_sees_order_and_other_master_does_not(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)

    assert temp_db.can_access_order(order_id, 500) is True
    assert temp_db.can_access_order(order_id, 501) is False
    assert [order['id'] for order in temp_db.get_master_orders(500)] == [order_id]
    assert temp_db.get_master_orders(501) == []


def test_shared_order_appears_with_marker(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)

    assert temp_db.grant_order_access(order_id, 501, granted_by=1) is True
    assert temp_db.grant_order_access(order_id, 501, granted_by=1) is False
    assert temp_db.can_access_order(order_id, 501) is True
    assert temp_db.get_order_access(order_id) == [501]

    shared = temp_db.get_master_orders(501)
    assert len(shared) == 1
    assert shared[0]['id'] == order_id
    assert shared[0]['is_shared'] == 1

    actions = [event['action'] for event in temp_db.get_order_events(order_id)]
    assert actions.count('access_granted') == 1


def test_revoke_order_access_removes_shared_order(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)
    temp_db.grant_order_access(order_id, 501, granted_by=1)

    assert temp_db.revoke_order_access(order_id, 501, revoked_by=1) is True
    assert temp_db.revoke_order_access(order_id, 501, revoked_by=1) is False

    assert temp_db.can_access_order(order_id, 501) is False
    assert temp_db.get_master_orders(501) == []
    actions = [event['action'] for event in temp_db.get_order_events(order_id)]
    assert 'access_revoked' in actions


def test_owner_does_not_need_shared_access(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)

    assert temp_db.grant_order_access(order_id, 500, granted_by=1) is False
    assert temp_db.get_order_access(order_id) == []


def test_deleted_order_cannot_be_shared(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)
    temp_db.soft_delete_order(order_id, 500, reason='test')

    with pytest.raises(ValueError):
        temp_db.grant_order_access(order_id, 501, granted_by=1)
    assert temp_db.can_access_order(order_id, 501) is False


def test_shared_order_can_be_printed_in_master_batch(temp_db):
    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)
    batch_id = temp_db.create_batch(501, '0217975')

    with pytest.raises(ValueError):
        temp_db.assign_orders_to_batch(batch_id, [order_id])

    temp_db.grant_order_access(order_id, 501, granted_by=1)
    assignment = temp_db.assign_orders_to_batch(batch_id, [order_id])[0]

    assert assignment['order_id'] == order_id
    assert assignment['ttn_number'] == '0217975'
    assert assignment['order_row'] == 25
    assert temp_db.get_order(order_id)['status'] == 'printed'


def test_get_recent_orders_skips_deleted_and_honours_limit(temp_db):
    first = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)
    second = temp_db.save_order(
        _order_data(2), master_id=500, driver_id=901)
    temp_db.soft_delete_order(first, 500, reason='test')

    recent = temp_db.get_recent_orders(limit=1)

    assert [order['id'] for order in recent] == [second]

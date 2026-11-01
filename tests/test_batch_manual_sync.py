import pytest

import orders_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_manual_sync.db"))
    orders_db.init_db()
    return orders_db


def _order_data(number):
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


def _batch_with_manual_rows(temp_db, start='0219200'):
    batch_id, _ = temp_db.create_batch_with_manual(
        500, start, _manual(start, 25))
    for ttn, row in (
        ('0219199', 24), ('0219198', 23), ('0219197', 22),
        ('0219196', 21), ('0219195', 20), ('0219194', 19),
    ):
        temp_db.add_manual_registry(500, batch_id, _manual(ttn, row))
    return batch_id


def test_manual_entries_update_counter_and_next_free_row(temp_db):
    batch_id = _batch_with_manual_rows(temp_db)

    batch = temp_db.get_batch(batch_id)
    assert batch['counter'] == 7
    assert temp_db.get_free_rows(batch_id, 500)[0] == 18

    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)
    assignment = temp_db.assign_orders_to_batch(batch_id, [order_id])[0]

    assert assignment['order_row'] == 18
    assert assignment['ttn_number'] == '0219193'
    assert temp_db.get_batch(batch_id)['counter'] == 8


def test_plan_preview_uses_rows_below_manual_entries(
    temp_db, tmp_path, monkeypatch
):
    import batch_print

    batch_id = _batch_with_manual_rows(temp_db)
    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)

    monkeypatch.setattr(
        batch_print, 'SELECTION_FILE', str(tmp_path / 'selection.json'))
    batch_print._reset_selection_cache()
    messages = []
    monkeypatch.setattr(
        batch_print.bot, 'send_message',
        lambda *args, **kwargs: messages.append((args, kwargs)))

    active = batch_print._active_batch_info(500)
    assert active['next_row'] == 18
    assert active['next_ttn'] == '0219193'

    batch_print.show_batch_plan(
        500, [order_id], '0219200', batch_id, active['counter'],
        occupied_rows=active['occupied_rows'])

    text = messages[0][0][1]
    assert 'стр. 18' in text
    assert '0219193' in text
    assert '0219199' not in text


def test_assign_rejects_changed_occupied_rows(temp_db):
    batch_id = temp_db.create_batch(500, '0219200')
    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)

    temp_db.add_manual_registry(500, batch_id, _manual('0219200', 25))

    with pytest.raises(ValueError):
        temp_db.assign_orders_to_batch(
            batch_id, [order_id], expected_rows=[])

    assert temp_db.get_order(order_id)['status'] == 'new'
    assert temp_db.get_batch(batch_id)['counter'] == 1


def test_manual_entry_rejects_occupied_row_and_duplicate_ttn(temp_db):
    batch_id, _ = temp_db.create_batch_with_manual(
        500, '0219200', _manual('0219200', 25))

    with pytest.raises(ValueError):
        temp_db.add_manual_registry(500, batch_id, _manual('0219199', 25))
    with pytest.raises(ValueError):
        temp_db.add_manual_registry(500, batch_id, _manual('0219200', 24))

    assert len(temp_db.get_manual_registry(500, batch_id)) == 1
    assert temp_db.get_batch(batch_id)['counter'] == 1


def test_repair_batch_layout_moves_overlapping_orders(temp_db):
    batch_id = _batch_with_manual_rows(temp_db)
    order_ids = [
        temp_db.save_order(
            _order_data(number), master_id=500, driver_id=900 + number)
        for number in range(1, 9)
    ]
    flawed = list(zip(
        order_ids,
        range(24, 16, -1),
        ('0219199', '0219198', '0219197', '0219196',
         '0219195', '0219194', '0219193', '0219192'),
    ))
    for order_id, row, ttn in flawed:
        temp_db.set_order_ttn(order_id, ttn, batch_id, row)
        temp_db.set_order_status(order_id, 'printed')

    preview = temp_db.repair_batch_layout(batch_id, dry_run=True)
    assert len(preview['moves']) == 6
    assert temp_db.get_order(flawed[0][0])['order_row'] == 24

    result = temp_db.repair_batch_layout(batch_id, dry_run=False)
    assert len(result['moves']) == 6
    assert temp_db.get_batch(batch_id)['counter'] == 15

    assignments = {
        order['id']: (order['order_row'], order['ttn_number'])
        for order in temp_db.get_batch_orders(batch_id)
    }
    assert assignments[flawed[0][0]] == (16, '0219191')
    assert assignments[flawed[5][0]] == (11, '0219186')
    assert assignments[flawed[6][0]] == (18, '0219193')
    assert assignments[flawed[7][0]] == (17, '0219192')

    manual = temp_db.get_manual_registry(500, batch_id)
    manual_pairs = {(entry['target_row'], entry['ttn_number']) for entry in manual}
    assert manual_pairs == {
        (25, '0219200'), (24, '0219199'), (23, '0219198'),
        (22, '0219197'), (21, '0219196'), (20, '0219195'),
        (19, '0219194'),
    }

    used_rows = [row for row, _ in assignments.values()]
    used_rows += [row for row, _ in manual_pairs]
    assert len(used_rows) == len(set(used_rows)) == 15

    used_ttns = [ttn for _, ttn in assignments.values()]
    used_ttns += [ttn for _, ttn in manual_pairs]
    assert len(used_ttns) == len(set(used_ttns)) == 15

    actions = [
        event['action'] for event in temp_db.get_recent_events(200)
    ]
    assert 'batch_repaired' in actions


def test_recalc_start_number_updates_manual_and_order_ttns(temp_db):
    batch_id = _batch_with_manual_rows(temp_db)
    order_id = temp_db.save_order(
        _order_data(1), master_id=500, driver_id=900)
    temp_db.assign_orders_to_batch(batch_id, [order_id])

    temp_db.recalc_batch_ttn(batch_id, '0219300')

    manual = {
        entry['target_row']: entry['ttn_number']
        for entry in temp_db.get_manual_registry(500, batch_id)
    }
    assert manual[25] == '0219300'
    assert manual[24] == '0219299'
    assert temp_db.get_order(order_id)['order_row'] == 18
    assert temp_db.get_order(order_id)['ttn_number'] == '0219293'
    assert temp_db.get_batch(batch_id)['counter'] == 8

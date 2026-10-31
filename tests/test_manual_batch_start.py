from types import SimpleNamespace

import pytest

import orders_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_batch_start.db"))
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


def _manual_entry():
    return {
        'ttn_number': '0217975', 'date': '22.10.26',
        'loading_point': 'Склад', 'driver_name': 'Петров П.П.',
        'car_plate': '7777 AB', 'target_row': 25,
    }


def test_create_batch_with_manual_reserves_top_row(temp_db):
    batch_id, entry_id = temp_db.create_batch_with_manual(
        500, '0217975', _manual_entry())

    batch = temp_db.get_batch(batch_id)
    assert batch['start_number'] == '0217975'
    assert batch['counter'] == 1

    manual = temp_db.get_manual_registry(500, batch_id)
    assert [entry['id'] for entry in manual] == [entry_id]
    assert manual[0]['ttn_number'] == '0217975'
    assert manual[0]['target_row'] == 25

    order_id = temp_db.save_order(
        _order_data(), master_id=500, driver_id=900)
    assignment = temp_db.assign_orders_to_batch(batch_id, [order_id])[0]

    assert assignment['ttn_number'] == '0217974'
    assert assignment['order_row'] == 24
    assert temp_db.get_batch(batch_id)['counter'] == 2


def test_create_batch_with_manual_refuses_second_active_batch(temp_db):
    first_batch = temp_db.create_batch(500, '0218000')

    with pytest.raises(ValueError):
        temp_db.create_batch_with_manual(500, '0217975', _manual_entry())

    active = temp_db.get_active_batch(500)
    assert active['id'] == first_batch
    assert active['counter'] == 0
    assert temp_db.get_manual_registry(500, first_batch) == []


def test_no_batch_screen_suggests_manual_start(monkeypatch):
    import registry

    sent = {}
    monkeypatch.setattr(registry.orders_db, 'get_active_batch', lambda uid: None)
    monkeypatch.setattr(
        registry, 'safe_edit_message_text',
        lambda **kwargs: sent.update(kwargs))

    registry.render_current_registry(100, message_id=5)

    assert 'с ручной накладной' in sent['text']
    callbacks = [
        button.callback_data
        for row in sent['reply_markup'].keyboard
        for button in row
    ]
    labels = [
        button.text
        for row in sent['reply_markup'].keyboard
        for button in row
    ]
    assert 'master_registry_start_manual' in callbacks
    assert any('Начать пачку с ручной накладной' in label for label in labels)


def test_start_manual_batch_flow_creates_batch(monkeypatch):
    import registry

    user_id = 100
    registry.master_edit_state.clear()
    sent = []
    created = {}

    monkeypatch.setattr(registry.orders_db, 'get_active_batch', lambda uid: None)
    monkeypatch.setattr(registry.bot, 'answer_callback_query', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        registry.bot, 'send_message',
        lambda *args, **kwargs: sent.append((args, kwargs)))
    monkeypatch.setattr(registry, 'render_current_registry',
                        lambda *args, **kwargs: None)

    def fake_create(master_id, start_number, entry):
        created.update(
            master_id=master_id, start_number=start_number, entry=entry)
        return 42, 7

    monkeypatch.setattr(
        registry.orders_db, 'create_batch_with_manual', fake_create)

    call = SimpleNamespace(
        id='callback-1',
        message=SimpleNamespace(
            chat=SimpleNamespace(id=user_id), message_id=5))

    registry.master_registry_start_manual(call)

    assert registry.master_edit_state[user_id]['start_batch'] is True
    assert registry.master_edit_state[user_id]['step'] == 'ttn'

    for text in ('0217975', '22.10.26', 'Склад', 'Петров П.П.', '7777 AB'):
        registry.handle_manual_reg(SimpleNamespace(
            chat=SimpleNamespace(id=user_id), text=text))

    assert created == {
        'master_id': user_id,
        'start_number': '0217975',
        'entry': {
            'ttn_number': '0217975',
            'date': '22.10.26',
            'loading_point': 'Склад',
            'driver_name': 'Петров П.П.',
            'car_plate': '7777 AB',
            'target_row': 25,
        },
    }
    assert user_id not in registry.master_edit_state
    assert any('строка 25' in str(args[1]) for args, _ in sent)


def test_start_manual_batch_requires_numeric_number(monkeypatch):
    import registry

    user_id = 100
    registry.master_edit_state.clear()
    registry.master_edit_state[user_id] = {
        'action': 'manual_reg', 'step': 'ttn', 'start_batch': True,
    }
    created = []
    monkeypatch.setattr(registry.orders_db, 'get_active_batch', lambda uid: None)
    monkeypatch.setattr(registry.bot, 'send_message', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        registry.orders_db, 'create_batch_with_manual',
        lambda *args, **kwargs: created.append(args))

    registry.handle_manual_reg(SimpleNamespace(
        chat=SimpleNamespace(id=user_id), text='ABC'))

    assert created == []
    assert registry.master_edit_state[user_id]['step'] == 'ttn'


def test_start_manual_batch_cancels_if_batch_appeared(monkeypatch):
    import registry

    user_id = 100
    registry.master_edit_state.clear()
    registry.master_edit_state[user_id] = {
        'action': 'manual_reg', 'step': 'ttn', 'start_batch': True,
    }
    created = []
    rendered = []
    monkeypatch.setattr(
        registry.orders_db, 'get_active_batch',
        lambda uid: {'id': 99, 'start_number': '0218000', 'counter': 0})
    monkeypatch.setattr(registry.bot, 'send_message', lambda *args, **kwargs: None)
    monkeypatch.setattr(registry, 'render_current_registry',
                        lambda *args, **kwargs: rendered.append(args))
    monkeypatch.setattr(
        registry.orders_db, 'create_batch_with_manual',
        lambda *args, **kwargs: created.append(args))

    registry.handle_manual_reg(SimpleNamespace(
        chat=SimpleNamespace(id=user_id), text='0217975'))

    assert created == []
    assert user_id not in registry.master_edit_state
    assert rendered

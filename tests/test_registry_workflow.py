from types import SimpleNamespace


def make_call(user_id=100, data='print_order_42'):
    return SimpleNamespace(
        id='callback-1',
        data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=user_id), message_id=5),
    )


def test_reprint_after_unprint_reuses_ttn(monkeypatch):
    import registry
    import master_menu

    order = {
        'id': 42, 'master_id': 100, 'ttn_number': '0217975',
        'order_row': 25, 'status': 'new', 'deleted_at': None,
        'date': '22.10.26', 'waybill_number': 'WB-1',
    }
    status_calls = []
    monkeypatch.setattr(registry.orders_db, 'get_order', lambda order_id: order)
    monkeypatch.setattr(registry.orders_db, 'set_order_status',
                        lambda order_id, status: status_calls.append((order_id, status)))
    monkeypatch.setattr(registry.orders_db, 'log_order_event',
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(
        registry.orders_db, 'get_active_batch',
        lambda user_id: (_ for _ in ()).throw(AssertionError('batch must not be touched')))
    monkeypatch.setattr(registry.bot, 'answer_callback_query',
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(master_menu, 'render_order_card',
                        lambda *args, **kwargs: None)

    registry.print_order(make_call())

    assert status_calls == [(42, 'printed')]


def test_unprint_keeps_assigned_ttn(monkeypatch):
    import registry
    import master_menu

    order = {
        'id': 42, 'master_id': 100, 'ttn_number': '0217975',
        'order_row': 25, 'status': 'printed', 'deleted_at': None,
    }
    status_calls = []
    monkeypatch.setattr(registry.orders_db, 'get_order', lambda order_id: order)
    monkeypatch.setattr(registry.orders_db, 'set_order_status',
                        lambda order_id, status: status_calls.append((order_id, status)))
    monkeypatch.setattr(registry.orders_db, 'log_order_event',
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(registry.bot, 'answer_callback_query',
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(master_menu, 'render_order_card',
                        lambda *args, **kwargs: None)

    registry.unprint_order(make_call(data='unprint_order_42'))

    assert status_calls == [(42, 'new')]
    assert order['ttn_number'] == '0217975'


def test_partial_registry_download_does_not_clear_manual_entries(monkeypatch, tmp_path):
    import registry

    batch = {'id': 7, 'start_number': '0217975', 'counter': 2,
             'started_at': '2026-10-22 10:00:00'}
    manual = [{'id': 1, 'ttn_number': '0217975', 'date': '22.10.26',
               'loading_point': 'Склад', 'driver_name': 'Петров',
               'car_plate': '7777 AB', 'target_row': 25}]
    cleared = []
    monkeypatch.setattr(registry.orders_db, 'get_active_batch', lambda uid: batch)
    monkeypatch.setattr(registry.orders_db, 'get_batch_orders', lambda bid: [])
    monkeypatch.setattr(registry.orders_db, 'get_manual_registry',
                        lambda uid, bid: manual)
    monkeypatch.setattr(registry.orders_db, 'clear_manual_registry',
                        lambda *args: cleared.append(args))
    docx = tmp_path / 'registry.docx'
    docx.write_bytes(b'test')
    monkeypatch.setattr(registry.registry_filler, 'generate_registry',
                        lambda *args: (str(docx), ''))
    monkeypatch.setattr(registry, 'render_current_registry', lambda *a, **k: None)
    monkeypatch.setattr(registry.bot, 'answer_callback_query',
                        lambda *a, **k: None)
    monkeypatch.setattr(registry.bot, 'send_document', lambda *a, **k: None)
    monkeypatch.setattr(registry.bot, 'send_message', lambda *a, **k: None)

    registry.master_registry_download(
        make_call(data='master_registry_download'))

    assert cleared == []

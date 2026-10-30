from pathlib import Path
from types import SimpleNamespace


def make_call(user_id):
    return SimpleNamespace(
        id='callback-confirm',
        data='confirm_order',
        message=SimpleNamespace(chat=SimpleNamespace(id=user_id), message_id=10),
    )


def make_data():
    return {
        'day': '22', 'month': '10', 'year': '26',
        'waybill_number': 'WB-1', 'car_model': 'МАЗ', 'car_plate': '1234 AB',
        'trailer_info': '-', 'loading_point': 'Склад', 'unloading_point': 'Объект',
        'driver_name': 'Иванов И.И.',
        'cargos': [{
            'cargo_name': 'Песок', 'trips': '1', 'unit': 'т',
            'quantity': '10', 'cargo_qty': '10', 'places': '2',
            'price': '100', 'vat_rate': 'Без НДС',
        }],
    }


def prepare(monkeypatch, save_calls, fail_word=False, mark_calls=None):
    import driver_order_summary as summary
    from config import user_data

    mark_calls = [] if mark_calls is None else mark_calls

    path = Path('fake_order.docx')
    path.write_bytes(b'test')

    def fill(data, name):
        if fail_word:
            raise RuntimeError('word failed')
        return None, None, str(path)

    monkeypatch.setattr(summary, 'fill_documents', fill)
    monkeypatch.setattr(summary, 'find_masters_by_loading', lambda loading: [777])
    monkeypatch.setattr(summary, 'safe_edit_message_text', lambda **kwargs: None)
    monkeypatch.setattr(summary, 'save_last_orders', lambda: None)
    monkeypatch.setattr(summary.orders_db, 'save_order',
                        lambda data, master_id, driver_id, **kwargs: (
                            save_calls.append((master_id, driver_id)) or len(save_calls)))
    monkeypatch.setattr(summary.orders_db, 'update_order_field',
                        lambda *args, **kwargs: None)
    monkeypatch.setattr(
        summary.orders_db, 'mark_order_delivery',
        lambda order_id, status, error=None: (
            mark_calls.append((order_id, status, error)) or True))
    monkeypatch.setattr(summary.bot, 'send_message',
                        lambda *args, **kwargs: SimpleNamespace(message_id=1))
    monkeypatch.setattr(summary.bot, 'send_document', lambda *args, **kwargs: None)
    monkeypatch.setattr(summary.bot, 'answer_callback_query',
                        lambda *args, **kwargs: None)
    return summary, user_data


def test_duplicate_confirm_saves_only_once(monkeypatch):
    save_calls = []
    summary, user_data = prepare(monkeypatch, save_calls)
    uid = 7001
    user_data[uid] = make_data()

    summary.confirm_order(make_call(uid))
    summary.confirm_order(make_call(uid))

    assert len(save_calls) == 1
    assert user_data[uid]['submitted'] is True


def test_word_failure_does_not_save_or_report_success(monkeypatch):
    save_calls = []
    summary, user_data = prepare(monkeypatch, save_calls, fail_word=True)
    uid = 7002
    user_data[uid] = make_data()
    sent = []
    monkeypatch.setattr(summary.bot, 'send_message',
                        lambda *args, **kwargs: sent.append(args) or SimpleNamespace(message_id=1))

    summary.confirm_order(make_call(uid))

    assert save_calls == []
    texts = [str(args[1]) for args in sent if len(args) > 1]
    assert any('НЕ отправлена' in text for text in texts)
    assert not any('Заявка отправлена мастеру' in text for text in texts)


def test_successful_delivery_is_marked_delivered(monkeypatch):
    mark_calls = []
    summary, user_data = prepare(monkeypatch, [], mark_calls=mark_calls)
    uid = 7003
    user_data[uid] = make_data()

    summary.confirm_order(make_call(uid))

    assert mark_calls == [(1, 'delivered', None)]


def test_document_failure_marks_delivery_failed(monkeypatch):
    mark_calls = []
    summary, user_data = prepare(monkeypatch, [], mark_calls=mark_calls)
    uid = 7004
    user_data[uid] = make_data()
    monkeypatch.setattr(
        summary.bot, 'send_document',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('network unavailable')))

    summary.confirm_order(make_call(uid))

    assert len(mark_calls) == 1
    order_id, status, error = mark_calls[0]
    assert order_id == 1
    assert status == 'failed'
    assert 'network unavailable' in error

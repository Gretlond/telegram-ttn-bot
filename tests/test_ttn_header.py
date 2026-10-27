def test_update_ttn_header_persists_all_fields(monkeypatch):
    import database

    monkeypatch.setattr(database, "TTN_HEADER", {})
    monkeypatch.setattr(database, "save_ttn_header", lambda: True)

    values = {
        "shipper": "ОАО «Отправитель»",
        "shipper_unp": "111111111",
        "consignee": "ОАО «Получатель»",
        "consignee_unp": "222222222",
        "customer": "ОАО «Заказчик»",
        "customer_unp": "333333333",
    }
    assert database.update_ttn_header(**values) is True
    assert database.TTN_HEADER == values


def test_update_ttn_header_rejects_unknown_field(monkeypatch):
    import database

    monkeypatch.setattr(database, "TTN_HEADER", {})
    monkeypatch.setattr(database, "save_ttn_header", lambda: True)

    assert database.update_ttn_header(unknown="value") is False
    assert database.TTN_HEADER == {}


def test_update_ttn_header_can_clear_value(monkeypatch):
    import database

    monkeypatch.setattr(database, "TTN_HEADER", {"shipper": "Старое значение"})
    monkeypatch.setattr(database, "save_ttn_header", lambda: True)

    assert database.update_ttn_header(shipper="") is True
    assert database.TTN_HEADER["shipper"] == ""

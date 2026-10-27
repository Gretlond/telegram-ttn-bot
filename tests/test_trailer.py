def test_add_trailer_accepts_number_without_model(monkeypatch):
    import database

    monkeypatch.setattr(database, "TRAILERS", {})
    monkeypatch.setattr(database, "save_trailers", lambda: None)

    tr_id = database.add_trailer("А 8584 В-4")

    assert database.TRAILERS[tr_id] == {
        "model": "",
        "plate": "А 8584 В-4",
    }
    assert database.trailer_number(database.TRAILERS[tr_id]) == "А 8584 В-4"

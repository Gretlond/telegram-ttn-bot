from types import SimpleNamespace

import database
import driver_order_cargo


def test_legacy_subcategory_inherits_material_distance():
    cargo = {"has_distance": True}

    assert database.subcategory_name("Грунт 1-й категории") == \
        "Грунт 1-й категории"
    assert database.subcategory_has_distance(
        cargo, "Грунт 1-й категории") is True
    assert database.subcategory_distance_is_custom(
        "Грунт 1-й категории") is False


def test_subcategory_can_override_distance():
    cargo = {"has_distance": True}
    value = {"name": "Грунт 2-й категории", "has_distance": False}

    assert database.subcategory_name(value) == "Грунт 2-й категории"
    assert database.subcategory_has_distance(cargo, value) is False
    assert database.subcategory_distance_is_custom(value) is True


def test_subcategory_can_enable_distance_when_material_has_it_off():
    cargo = {"has_distance": False}
    value = {"name": "Особый груз", "has_distance": True}

    assert database.subcategory_has_distance(cargo, value) is True


def _use_temp_cargo_types(monkeypatch):
    store = {
        "ground": {
            "name": "Грунт",
            "has_distance": True,
            "subcategories": {
                "sub_1": "Грунт 1-й категории",
                "sub_2": {"name": "Грунт 2-й категории",
                          "has_distance": False},
            },
        },
    }
    monkeypatch.setattr(database, "CARGO_TYPES", store)
    monkeypatch.setattr(database, "save_cargo_types", lambda: None)
    return store


def test_rename_preserves_distance_override(monkeypatch):
    store = _use_temp_cargo_types(monkeypatch)

    assert database.update_subcategory(
        "ground", "sub_2", "Грунт 2-й категории (новый)") is True

    assert store["ground"]["subcategories"]["sub_2"] == {
        "name": "Грунт 2-й категории (новый)",
        "has_distance": False,
    }


def test_set_and_reset_subcategory_distance(monkeypatch):
    store = _use_temp_cargo_types(monkeypatch)

    assert database.set_subcategory_distance(
        "ground", "sub_1", False) is True
    assert store["ground"]["subcategories"]["sub_1"] == {
        "name": "Грунт 1-й категории",
        "has_distance": False,
    }

    assert database.reset_subcategory_distance(
        "ground", "sub_1") is True
    assert store["ground"]["subcategories"]["sub_1"] == \
        "Грунт 1-й категории"


def test_add_subcategory_with_distance_choice(monkeypatch):
    store = _use_temp_cargo_types(monkeypatch)

    no_dist = database.add_subcategory("ground", "Без расстояния", False)
    inherit = database.add_subcategory("ground", "Как у материала")

    subs = store["ground"]["subcategories"]
    assert subs[no_dist] == {
        "name": "Без расстояния", "has_distance": False}
    assert subs[inherit] == "Как у материала"


def test_subcategory_keyboard_shows_dict_name(monkeypatch):
    import keyboards

    _use_temp_cargo_types(monkeypatch)
    monkeypatch.setattr(keyboards, "CARGO_TYPES", database.CARGO_TYPES)

    markup = keyboards.get_cargo_subcategory_keyboard("ground")
    labels = [button.text for row in markup.keyboard for button in row]

    assert "Грунт 2-й категории" in labels


class FakeBot:
    def __init__(self):
        self.answers = []

    def answer_callback_query(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _call(data):
    return SimpleNamespace(
        id="callback",
        data=data,
        message=SimpleNamespace(
            chat=SimpleNamespace(id=42),
            message_id=7,
        ),
    )


def _prepare_driver(monkeypatch, cargo_types):
    user_data = {42: {}}
    finals = []
    edits = []
    monkeypatch.setattr(driver_order_cargo, "CARGO_TYPES", cargo_types)
    monkeypatch.setattr(driver_order_cargo, "user_data", user_data)
    monkeypatch.setattr(driver_order_cargo, "bot", FakeBot())
    monkeypatch.setattr(
        driver_order_cargo, "safe_edit_message_text",
        lambda **kwargs: edits.append(kwargs))
    monkeypatch.setattr(
        driver_order_cargo, "finalize_cargo",
        lambda uid, message_id=None: finals.append((uid, message_id)))
    return user_data, finals, edits


def test_driver_does_not_ask_distance_for_overridden_subcategory(monkeypatch):
    cargo_types = {
        "ground": {
            "name": "Грунт",
            "has_distance": True,
            "subcategories": {
                "ground_2": {"name": "Грунт 2-й категории",
                             "has_distance": False},
            },
        },
    }
    user_data, finals, edits = _prepare_driver(monkeypatch, cargo_types)

    driver_order_cargo.handle_cargo_subcategory(
        _call("cargo_sub::ground::ground_2"))

    assert user_data[42]["cargo_sub"] == "Грунт 2-й категории"
    assert finals == [(42, 7)]
    assert edits == []


def test_driver_asks_distance_when_subcategory_inherits(monkeypatch):
    cargo_types = {
        "ground": {
            "name": "Грунт",
            "has_distance": True,
            "subcategories": {"ground_1": "Грунт 1-й категории"},
        },
    }
    user_data, finals, edits = _prepare_driver(monkeypatch, cargo_types)

    driver_order_cargo.handle_cargo_subcategory(
        _call("cargo_sub::ground::ground_1"))

    assert user_data[42]["cargo_sub"] == "Грунт 1-й категории"
    assert finals == []
    assert len(edits) == 1
    assert "Выберите расстояние" in edits[0]["text"]

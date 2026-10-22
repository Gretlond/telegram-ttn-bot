from types import SimpleNamespace

import pytest


def make_message(user_id, text):
    return SimpleNamespace(chat=SimpleNamespace(id=user_id), text=text)


@pytest.fixture
def bot_calls(monkeypatch):
    """Перехватывает отправку сообщений и регистрацию next-step обработчиков."""
    from config import bot

    sent = []
    by_chat = []
    by_message = []

    def send_message(*args, **kwargs):
        sent.append((args, kwargs))
        return SimpleNamespace(message_id=1)

    monkeypatch.setattr(bot, "send_message", send_message)
    monkeypatch.setattr(bot, "register_next_step_handler_by_chat_id",
                        lambda chat_id, fn, *a, **k: by_chat.append((chat_id, fn)))
    monkeypatch.setattr(bot, "register_next_step_handler",
                        lambda message, fn, *a, **k: by_message.append((message, fn)))

    return SimpleNamespace(sent=sent, by_chat=by_chat, by_message=by_message)


@pytest.fixture
def platform_module():
    import driver_order_platform
    return driver_order_platform


@pytest.fixture
def cargo_module():
    import driver_order_cargo
    return driver_order_cargo


@pytest.fixture
def start_module():
    import driver_order_start
    return driver_order_start


@pytest.fixture
def summary_module():
    import driver_order_summary
    return driver_order_summary


def last_sent_text(calls):
    assert calls.sent
    args, _ = calls.sent[-1]
    return args[1] if len(args) > 1 else ""


def test_platform_places_valid_and_invalid(bot_calls, platform_module):
    p = platform_module
    uid = 101
    p.user_data[uid] = {"temp_qty": "2.5"}

    p.get_platform_places(make_message(uid, "abc"))
    assert p.user_data[uid].get("temp_places") is None
    assert "целое число" in last_sent_text(bot_calls)
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_places)

    p.user_data[uid] = {}
    p.get_platform_places(make_message(uid, "11"))
    assert p.user_data[uid]["temp_places"] == "11"
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_mass)


def test_platform_quantity_valid_and_invalid(bot_calls, platform_module):
    p = platform_module
    uid = 102
    p.user_data[uid] = {}

    p.get_platform_cargo_qty(make_message(uid, "abc"))
    assert "Введите число" in last_sent_text(bot_calls)
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_cargo_qty)

    p.user_data[uid] = {}
    p.get_platform_cargo_qty(make_message(uid, "2,5"))
    assert p.user_data[uid]["temp_qty"] == "2.5"
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_places)


def test_platform_mass_invalid_and_valid(bot_calls, platform_module):
    p = platform_module
    uid = 103
    p.user_data[uid] = {}

    p.get_platform_mass(make_message(uid, "abc"))
    assert "Введите массу" in last_sent_text(bot_calls)
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_mass)

    p.user_data[uid] = {
        "temp_cargo_name": "Песок",
        "temp_unit": "тн",
        "temp_qty": "10",
        "temp_places": "5",
    }
    p.get_platform_mass(make_message(uid, "20"))
    cargo = p.user_data[uid]["cargos"][0]
    assert cargo["cargo_name"] == "Песок"
    assert cargo["unit"] == "тн"
    assert cargo["quantity"] == "10"
    assert cargo["places"] == "5"
    assert cargo["cargo_qty"] == "20"


def test_platform_handlers_survive_non_text(bot_calls, platform_module):
    p = platform_module
    uid = 104
    p.user_data[uid] = {}

    p.get_platform_cargo_qty(make_message(uid, None))
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_cargo_qty)

    p.get_platform_places(make_message(uid, None))
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_places)

    p.get_platform_mass(make_message(uid, None))
    assert bot_calls.by_chat[-1] == (uid, p.get_platform_mass)


def test_standard_trips_valid_invalid_and_non_text(bot_calls, cargo_module):
    c = cargo_module
    from database import CARS

    car_id, car = next((k, v) for k, v in CARS.items() if v.get("capacity"))
    uid = 105
    c.user_data[uid] = {"car_id": car_id, "temp_cargo_name": "Песок"}

    c.get_trips(make_message(uid, "abc"))
    assert "Введите число" in last_sent_text(bot_calls)
    assert bot_calls.by_message[-1][1] is c.get_trips

    c.get_trips(make_message(uid, None))
    assert bot_calls.by_message[-1][1] is c.get_trips

    c.user_data[uid] = {"car_id": car_id, "temp_cargo_name": "Песок"}
    c.get_trips(make_message(uid, "2"))
    assert c.user_data[uid]["temp_trips"] == "2"
    assert c.user_data[uid]["temp_cargo_qty"]


def test_waybill_empty_value_is_asked_again(bot_calls, start_module):
    s = start_module
    uid = 106
    s.user_data[uid] = {}

    s.get_waybill_number(make_message(uid, "   "))
    assert "номер путевого" in last_sent_text(bot_calls)
    assert bot_calls.by_chat[-1] == (uid, s.get_waybill_number)

    s.get_waybill_number(make_message(uid, " 123 "))
    assert s.user_data[uid]["waybill_number"] == "123"


def test_custom_date_valid_invalid_and_non_text(bot_calls, start_module):
    s = start_module
    uid = 107
    s.user_data[uid] = {}

    s.get_custom_date(make_message(uid, "32.13.26"))
    assert "Неверный формат" in last_sent_text(bot_calls)
    assert bot_calls.by_message[-1][1] is s.get_custom_date

    s.get_custom_date(make_message(uid, None))
    assert bot_calls.by_message[-1][1] is s.get_custom_date

    s.get_custom_date(make_message(uid, "22.10.26"))
    assert (s.user_data[uid]["day"], s.user_data[uid]["month"],
            s.user_data[uid]["year"]) == ("22", "10", "26")


def test_edit_cargo_handlers_survive_non_text(bot_calls, summary_module):
    m = summary_module
    uid = 108
    m.user_data[uid] = {
        "editing_cargo_idx": 0,
        "cargos": [{"cargo_name": "Песок", "cargo_qty": "10", "trips": "1"}],
    }

    m.save_edit_cargo_trips(make_message(uid, None))
    assert "Введите число" in last_sent_text(bot_calls)
    assert bot_calls.by_message[-1][1] is m.save_edit_cargo_trips

    m.save_edit_cargo_mass(make_message(uid, None))
    assert bot_calls.by_message[-1][1] is m.save_edit_cargo_mass

import pytest

import orders_db
from pricing import billable_quantity, calculate_cargo_cost, uses_quantity_for_cost
from utils import calculate_vat_totals


def test_piece_unit_uses_quantity():
    cargo = {
        "unit": "шт",
        "quantity": "4",
        "cargo_qty": "0.0004",
        "price": "3.0",
    }

    assert uses_quantity_for_cost(cargo["unit"]) is True
    assert billable_quantity(cargo) == 4
    assert calculate_cargo_cost(cargo) == 12.0


def test_piece_unit_with_dot_uses_quantity():
    cargo = {
        "unit": "шт.",
        "quantity": "2",
        "cargo_qty": "0.02",
        "price": "45.1",
    }

    assert calculate_cargo_cost(cargo) == 90.2


def test_piece_unit_without_quantity_falls_back_to_mass():
    cargo = {"unit": "шт", "cargo_qty": "2.5", "price": "10"}

    assert billable_quantity(cargo) == 2.5
    assert calculate_cargo_cost(cargo) == 25.0


def test_ton_unit_still_uses_mass():
    cargo = {
        "unit": "тн",
        "quantity": "4",
        "cargo_qty": "0.045",
        "price": "85.31",
    }

    assert uses_quantity_for_cost(cargo["unit"]) is False
    assert billable_quantity(cargo) == 0.045
    assert calculate_cargo_cost(cargo) == 3.84


def test_volume_unit_uses_quantity():
    cargo = {
        "unit": "м³",
        "quantity": "2.5",
        "cargo_qty": "4.8",
        "price": "1200",
    }

    assert uses_quantity_for_cost(cargo["unit"]) is True
    assert calculate_cargo_cost(cargo) == 3000.0


def test_calculate_vat_totals_piece_unit_falls_back_to_quantity():
    cargos = [{
        "unit": "шт",
        "quantity": "4",
        "cargo_qty": "0.02",
        "price": "45.1",
        "vat_rate": "20%",
    }]

    assert calculate_vat_totals(cargos) == (180.4, 36.08, 216.48)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_db, "DB_FILE", str(tmp_path / "test_pricing.db"))
    orders_db.init_db()
    return orders_db


def _order_data(cargos):
    return {
        "day": "11", "month": "11", "year": "26",
        "waybill_number": "4444",
        "car_model": "МАЗ", "car_plate": "1234 AB",
        "trailer_info": "-",
        "loading_point": "Склад", "unloading_point": "Объект",
        "driver_name": "Иванов И.И.",
        "cargos": cargos,
    }


def test_recalculate_order_totals_counts_pieces_not_mass(temp_db):
    order_id = temp_db.save_order(_order_data([
        {"cargo_name": "Диск", "unit": "шт", "quantity": "1",
         "cargo_qty": "0.001", "price": "155.84", "vat_rate": "Без НДС"},
        {"cargo_name": "Замок", "unit": "шт", "quantity": "4",
         "cargo_qty": "0.0004", "price": "3.0", "vat_rate": "Без НДС"},
        {"cargo_name": "Отвод", "unit": "шт", "quantity": "4",
         "cargo_qty": "0.02", "price": "45.1", "vat_rate": "Без НДС"},
        {"cargo_name": "Тройник", "unit": "шт", "quantity": "2",
         "cargo_qty": "0.001", "price": "19.23", "vat_rate": "Без НДС"},
    ]), master_id=500, driver_id=900)

    total_cost, total_with_vat = temp_db.recalculate_order_totals(order_id)

    assert total_cost == 386.7
    assert total_with_vat == 386.7


def test_recalculate_order_totals_keeps_mass_for_tons(temp_db):
    order_id = temp_db.save_order(_order_data([
        {"cargo_name": "Решётка", "unit": "тн", "quantity": "4",
         "cargo_qty": "0.045", "price": "85.31", "vat_rate": "Без НДС"},
        {"cargo_name": "Кран", "unit": "тн", "quantity": "4",
         "cargo_qty": "0.004", "price": "34.78", "vat_rate": "Без НДС"},
    ]), master_id=500, driver_id=900)

    total_cost, total_with_vat = temp_db.recalculate_order_totals(order_id)

    assert total_cost == 3.98
    assert total_with_vat == 3.98

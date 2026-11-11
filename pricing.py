# =============================================================
# РАСЧЁТ КОЛИЧЕСТВА И СТОИМОСТИ ГРУЗА
# =============================================================
"""Единая формула: цена умножается на количество в выбранной единице.

Для штучного товара количество хранится в поле ``quantity``.
Для массы (``тн``) и старых записей без ``quantity`` используется
``cargo_qty``, поэтому ранее сохранённые заявки считаются как раньше.
"""


def parse_amount(value):
    """Безопасно приводит сумму/число из БД или анкеты к float."""
    try:
        return float(str(value if value is not None else '0')
                     .replace(',', '.').replace(' ', '').strip())
    except (ValueError, TypeError):
        return 0.0


def is_piece_unit(unit):
    """Является ли единица измерения штучной (``шт``, ``шт.``)."""
    normalized = str(unit or '').strip().lower().replace('.', '')
    return normalized in ('шт', 'штук')


def billable_quantity(cargo):
    """Количество, на которое умножается цена.

    ``шт`` -> ``quantity`` (количество штук);
    ``тн`` и остальные единицы -> ``cargo_qty`` (масса);
    если ``quantity`` нет, используется ``cargo_qty``.
    """
    quantity = cargo.get('quantity')
    if is_piece_unit(cargo.get('unit')) and str(quantity or '').strip():
        return parse_amount(quantity)
    return parse_amount(cargo.get('cargo_qty'))


def calculate_cargo_cost(cargo):
    """Стоимость строки груза без НДС."""
    return round(billable_quantity(cargo) * parse_amount(cargo.get('price')), 2)


def refresh_cargo_cost(cargo):
    """Пересчитывает сохранённые итоги строки, если задана цена.

    Возвращает ``True``, если цена есть и значения были обновлены.
    """
    if str(cargo.get('price', '') or '').strip() == '':
        return False
    total_cost = calculate_cargo_cost(cargo)
    vat_rate = str(cargo.get('vat_rate', '') or '').strip()
    vat_cost = round(total_cost * 0.20, 2) if vat_rate == '20%' else 0.0
    cargo['total_cost'] = total_cost
    cargo['vat_cost'] = vat_cost
    cargo['total_with_vat'] = round(total_cost + vat_cost, 2)
    return True

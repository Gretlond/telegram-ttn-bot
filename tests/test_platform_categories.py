from keyboards import (get_platform_cargos_keyboard,
                       get_platform_categories_keyboard)


def _callbacks(markup):
    return [button.callback_data
            for row in markup.keyboard for button in row]


def test_admin_can_add_category_from_platform_screen():
    callbacks = _callbacks(get_platform_categories_keyboard(admin=True))

    assert "p_cat_add" in callbacks


def test_driver_does_not_see_add_category_button():
    callbacks = _callbacks(get_platform_categories_keyboard())

    assert "p_cat_add" not in callbacks


def test_admin_can_add_cargo_from_category_screen():
    callbacks = _callbacks(get_platform_cargos_keyboard("cat_2", admin=True))

    assert "p_cargo_add::cat_2" in callbacks


def test_driver_does_not_see_add_cargo_button():
    callbacks = _callbacks(get_platform_cargos_keyboard("cat_2"))

    assert "p_cargo_add::cat_2" not in callbacks

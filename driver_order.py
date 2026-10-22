# =============================================================
# ВОДИТЕЛЬ: ТОЧКА ВХОДА
# =============================================================
# Обработчики регистрируются при импорте модулей. Bot.py по-прежнему
# импортирует только handle_driver_button из этого файла.
import driver_order_ui  # noqa: F401
import driver_order_start  # noqa: F401
import driver_order_platform  # noqa: F401
import driver_order_cargo  # noqa: F401
import driver_order_summary  # noqa: F401

from driver_order_start import handle_driver_button

__all__ = ['handle_driver_button']

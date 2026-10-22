"""Устанавливает демонстрационный шаблон ТТН.

Раньше этот файл генерировал шаблон с docxtpl-тегами, но текущий
``word_filler`` работает с python-docx и копирует cargo-строку напрямую.
Поэтому актуальный демо-шаблон лежит в ``assets/Шаблон_ТТН_демо.docx``.
"""
from pathlib import Path
import shutil

TARGET = Path("Шаблоны") / "Шаблон_ТТН.docx"
DEMO = Path("assets") / "Шаблон_ТТН_демо.docx"


def create_template() -> Path:
    """Копирует демо-шаблон в рабочую папку, не перезаписывая готовый файл."""
    if TARGET.exists():
        print(f"Шаблон уже существует: {TARGET}. Файл не изменён.")
        return TARGET

    if not DEMO.exists():
        raise FileNotFoundError(
            f"Не найден демонстрационный шаблон: {DEMO}. "
            "Проверьте, что репозиторий склонирован полностью."
        )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEMO, TARGET)
    print(f"Демонстрационный шаблон установлен: {TARGET}")
    return TARGET


if __name__ == "__main__":
    create_template()

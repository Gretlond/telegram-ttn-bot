import os
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# config.py читает эти переменные при импорте, а тесты импортируют модули бота.
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("YOUR_TELEGRAM_ID", "1")


@pytest.fixture(scope="session", autouse=True)
def runtime_dir(tmp_path_factory):
    """Изолирует рабочие файлы бота (data/, orders.db, Результат/) от проекта."""
    runtime = tmp_path_factory.mktemp("bot-runtime")

    template = PROJECT_ROOT / "Шаблоны" / "Шаблон_ТТН.docx"
    if not template.exists():
        template = PROJECT_ROOT / "assets" / "Шаблон_ТТН_демо.docx"
    if template.exists():
        target = runtime / "Шаблоны" / "Шаблон_ТТН.docx"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, target)

    old_cwd = Path.cwd()
    os.chdir(runtime)
    try:
        yield runtime
    finally:
        os.chdir(old_cwd)

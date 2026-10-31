# =============================================================
# ЛОГИРОВАНИЕ: ФАЙЛ С РОТАЦИЕЙ + STDERR (JOURNALD)
# =============================================================
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
CONSOLE_FORMAT = "%(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _log_to_file_enabled():
    raw = os.environ.get("TTN_LOG_TO_FILE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _resolve_level(value=None):
    raw = value if value is not None else os.environ.get("TTN_LOG_LEVEL", "INFO")
    if isinstance(raw, int):
        return raw
    return getattr(logging, str(raw).strip().upper(), logging.INFO)


def _remove_own_handlers(root):
    for handler in list(root.handlers):
        if getattr(handler, "_ttn_handler", False):
            root.removeHandler(handler)
            handler.close()


def setup_logging(level=None, log_file=None, max_bytes=None,
                  backup_count=None, force=False):
    """Настраивает корневой логгер: stderr (journald) и файл с ротацией.

    Повторные вызовы без force ничего не делают. Возвращает путь к файлу
    лога или None, если файловое логирование отключено.
    """
    global _configured
    if _configured and not force:
        return LOG_FILE if _log_to_file_enabled() else None

    root = logging.getLogger()
    _remove_own_handlers(root)
    root.setLevel(_resolve_level(level))

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    console._ttn_handler = True
    root.addHandler(console)

    path = None
    if _log_to_file_enabled():
        path = log_file or LOG_FILE
        try:
            folder = os.path.dirname(os.path.abspath(path))
            os.makedirs(folder, exist_ok=True)
            file_handler = RotatingFileHandler(
                path,
                maxBytes=max_bytes or MAX_BYTES,
                backupCount=backup_count if backup_count is not None
                else BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(
                logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
            file_handler._ttn_handler = True
            root.addHandler(file_handler)
        except OSError as e:
            path = None
            print(f"⚠️ Не удалось открыть лог-файл: {e}", file=sys.stderr)

    _configured = True
    return path


def reset_logging():
    """Убирает установленные ботом обработчики (используется в тестах)."""
    global _configured
    _remove_own_handlers(logging.getLogger())
    _configured = False


def get_logger(name=None):
    """Возвращает логгер модуля и гарантированно настраивает логирование."""
    setup_logging()
    return logging.getLogger(name)

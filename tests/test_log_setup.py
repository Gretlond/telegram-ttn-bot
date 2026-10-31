import logging
from logging.handlers import RotatingFileHandler

import pytest

import log_setup


@pytest.fixture(autouse=True)
def restore_logging():
    log_setup.reset_logging()
    yield
    log_setup.reset_logging()


def _own_handlers():
    return [
        handler for handler in logging.getLogger().handlers
        if getattr(handler, "_ttn_handler", False)
    ]


def test_setup_logging_writes_to_rotating_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TTN_LOG_TO_FILE", "1")
    log_path = tmp_path / "bot.log"

    result = log_setup.setup_logging(
        level="INFO", log_file=str(log_path), force=True)

    assert result == str(log_path)
    log_setup.get_logger("test").info("hello log")
    for handler in _own_handlers():
        handler.flush()

    assert log_path.exists()
    assert "hello log" in log_path.read_text(encoding="utf-8")

    file_handlers = [
        handler for handler in _own_handlers()
        if isinstance(handler, RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == log_setup.MAX_BYTES
    assert file_handlers[0].backupCount == log_setup.BACKUP_COUNT


def test_file_handler_rotates(tmp_path, monkeypatch):
    monkeypatch.setenv("TTN_LOG_TO_FILE", "1")
    log_path = tmp_path / "bot.log"
    log_setup.setup_logging(
        level="INFO", log_file=str(log_path), max_bytes=200,
        backup_count=1, force=True)

    logger = log_setup.get_logger("rotation")
    for index in range(50):
        logger.info("%s %s", "x" * 100, index)
    for handler in _own_handlers():
        handler.flush()

    assert log_path.exists()
    assert (tmp_path / "bot.log.1").exists()


def test_file_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("TTN_LOG_TO_FILE", "0")
    log_path = tmp_path / "bot.log"

    result = log_setup.setup_logging(
        level="WARNING", log_file=str(log_path), force=True)

    assert result is None
    assert not log_path.exists()
    assert not any(
        isinstance(handler, RotatingFileHandler) for handler in _own_handlers())


def test_setup_logging_always_writes_to_stderr(monkeypatch):
    monkeypatch.setenv("TTN_LOG_TO_FILE", "0")

    log_setup.setup_logging(level="DEBUG", force=True)

    console_handlers = [
        handler for handler in _own_handlers()
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, RotatingFileHandler)
    ]
    assert len(console_handlers) == 1


def test_reset_logging_removes_bot_handlers(monkeypatch):
    monkeypatch.setenv("TTN_LOG_TO_FILE", "0")
    log_setup.setup_logging(level="INFO", force=True)
    assert _own_handlers()

    log_setup.reset_logging()

    assert _own_handlers() == []

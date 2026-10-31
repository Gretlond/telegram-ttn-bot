# =============================================================
# ТОЧКА ВХОДА
# =============================================================
from config import bot, user_data
from keyboards import get_main_keyboard


@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.chat.id
    user_data[user_id] = {}
    bot.send_message(user_id,
                     "👋 Добро пожаловать!\n\n"
                     "Выберите вашу роль с помощью кнопок внизу экрана.",
                     reply_markup=get_main_keyboard())


# =============================================================
# РЕГИСТРАЦИЯ REPLY-КНОПОК
# =============================================================
from master_menu import handle_master_button
from driver_order import handle_driver_button


@bot.message_handler(func=lambda m: m.text == "🚛 Я водитель")
def _driver_button(message):
    handle_driver_button(message)


@bot.message_handler(func=lambda m: m.text == "👨‍💼 Я мастер")
def _master_button(message):
    handle_master_button(message)


# =============================================================
# ИМПОРТ ВСЕХ МОДУЛЕЙ — КАЖДЫЙ РЕГИСТРИРУЕТ СВОИ ХЭНДЛЕРЫ
# =============================================================
import master_menu
import master_edit
import registry
import batch_print
import driver_reg
import driver_order
import admin_menu


# =============================================================
# РЕГИСТРАЦИЯ АДМИН-МЕНЮ
# =============================================================
from config import MASTERS, save_masters, YOUR_TELEGRAM_ID
admin_menu.register(bot, MASTERS, save_masters, YOUR_TELEGRAM_ID)


# =============================================================
# ЗАПУСК
# =============================================================
import time
import requests
import health

from log_setup import get_logger

logger = get_logger(__name__)

def notify_backup_problems():
    """При старте сразу сообщаем администратору о проблеме автобэкапа."""
    try:
        alert = health.get_backup_alert()
        if alert:
            bot.send_message(YOUR_TELEGRAM_ID, alert)
    except Exception as e:
        logger.exception(f"⚠️ Не удалось проверить автобэкап: {e}")


if __name__ == "__main__":
    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    notify_backup_problems()

    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except requests.exceptions.ConnectionError as e:
            logger.exception(f"⚠️ Потеря связи с Telegram: {e}")
            logger.info("⏳ Переподключение через 10 секунд...")
            time.sleep(10)
        except requests.exceptions.ReadTimeout:
            logger.warning("⚠️ Таймаут чтения. Переподключение через 5 секунд...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"⚠️ Неожиданная ошибка: {e}")
            logger.info("⏳ Перезапуск через 10 секунд...")
            time.sleep(10)
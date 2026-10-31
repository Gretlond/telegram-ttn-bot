# =============================================================
# УТИЛИТЫ
# =============================================================
from config import bot, MASTERS, YOUR_TELEGRAM_ID
from database import LOCATIONS

from log_setup import get_logger

logger = get_logger(__name__)

def safe_edit_message_text(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    try:
        if reply_markup is not None:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                  parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                  parse_mode=parse_mode)
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.exception(f"⚠️ safe_edit: {e}")


def parse_order_index(rest):
    parts = rest.split('_')
    if len(parts) < 2:
        return None, None
    try:
        return int(parts[0]), int(parts[-1])
    except (ValueError, IndexError):
        return None, None


_UNITS_MALE = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
_UNITS_FEMALE = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
_TEENS = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
          'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
_TENS = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
         'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
_HUNDREDS = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
             'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']

# (значение, формы, женский род для счётного слова)
_SCALES = [
    (10 ** 12, ('триллион', 'триллиона', 'триллионов'), False),
    (10 ** 9, ('миллиард', 'миллиарда', 'миллиардов'), False),
    (10 ** 6, ('миллион', 'миллиона', 'миллионов'), False),
    (10 ** 3, ('тысяча', 'тысячи', 'тысяч'), True),
    (1, ('', '', ''), False),
]


def _plural_form(number, forms):
    """Выбирает форму слова для числа: 1 тысяча, 2 тысячи, 5 тысяч."""
    number = abs(int(number)) % 100
    if 11 <= number <= 14:
        return forms[2]
    number %= 10
    if number == 1:
        return forms[0]
    if 2 <= number <= 4:
        return forms[1]
    return forms[2]


def _under_1000_to_words(number, female=False):
    if number == 0:
        return ''
    result = []
    if number >= 100:
        result.append(_HUNDREDS[number // 100])
        number %= 100
    if 10 <= number < 20:
        result.append(_TEENS[number - 10])
    else:
        if number >= 20:
            result.append(_TENS[number // 10])
            number %= 10
        if number > 0:
            result.append(_UNITS_FEMALE[number] if female else _UNITS_MALE[number])
    return ' '.join(result)


def _int_to_words(number, female=False):
    """Целое число прописью, включая тысячи, миллионы и миллиарды."""
    number = int(number)
    if number == 0:
        return 'ноль'
    if number < 0:
        return 'минус ' + _int_to_words(-number, female=female)
    if number >= 10 ** 15:
        return str(number)

    parts = []
    for value, forms, scale_female in _SCALES:
        if number < value:
            continue
        count = number // value
        number %= value
        if value == 1:
            parts.append(_under_1000_to_words(count, female=female))
        else:
            parts.append(
                f"{_under_1000_to_words(count, female=scale_female)} "
                f"{_plural_form(count, forms)}"
            )
    return ' '.join(part for part in parts if part)


def number_to_text(number_str):
    try:
        number_str = str(number_str).replace(',', '.').strip()
        number = float(number_str)
        integer_part = int(number)
        fractional_part = round(abs(number - integer_part), 10)
        text_integer = _int_to_words(integer_part)
        if fractional_part == 0:
            return text_integer

        fractional_str = f"{fractional_part:.10f}".rstrip('0').split('.')[1]
        fractional_int = int(fractional_str)
        digits_count = len(fractional_str)
        if digits_count == 1:
            rank_singular, rank_plural = "десятая", "десятых"
        elif digits_count == 2:
            rank_singular, rank_plural = "сотая", "сотых"
        elif digits_count == 3:
            rank_singular, rank_plural = "тысячная", "тысячных"
        else:
            rank_singular, rank_plural = "десятитысячная", "десятитысячных"
        last_two = fractional_int % 100
        last_digit = fractional_int % 10
        if last_two in (11, 12, 13, 14):
            rank = rank_plural
        elif last_digit == 1:
            rank = rank_singular
        else:
            rank = rank_plural
        text_fractional = _int_to_words(fractional_int, female=True)
        return f"{text_integer} целых {text_fractional} {rank}"
    except Exception as e:
        logger.exception(f"Ошибка преобразования числа: {e}")
        return str(number_str)


def calculate_total_mass_text(cargos):
    total_mass = 0.0
    for c in cargos:
        try:
            qs = str(c.get('cargo_qty', '0')).replace(',', '.').strip()
            if qs:
                total_mass += float(qs)
        except (ValueError, AttributeError):
            pass
    if total_mass > 0:
        if total_mass == int(total_mass):
            total_mass_str = str(int(total_mass))
        else:
            total_mass_str = f"{total_mass:.2f}".rstrip('0').rstrip('.').replace('.', ',')
        total_mass_text = number_to_text(total_mass_str) + " тонн"
    else:
        total_mass_str = ''
        total_mass_text = ''
    return total_mass_str, total_mass_text


def parse_amount(value):
    """Безопасно приводит сумму/число из БД или анкеты к float."""
    try:
        return float(str(value if value is not None else '0')
                     .replace(',', '.').replace(' ', '').strip())
    except (ValueError, TypeError):
        return 0.0


def calculate_vat_totals(cargos):
    """Суммирует стоимость, НДС и стоимость с НДС по всем грузам.

    Сначала берутся уже рассчитанные значения строки (total_cost, vat_cost,
    total_with_vat). Если их нет — сумма восстанавливается по массе и цене.
    """
    total_cost = 0.0
    total_vat = 0.0
    total_with_vat = 0.0
    for c in cargos or []:
        cost = parse_amount(c.get('total_cost'))
        vat = parse_amount(c.get('vat_cost'))
        with_vat = parse_amount(c.get('total_with_vat'))

        if cost == 0 and with_vat == 0:
            qty = parse_amount(c.get('cargo_qty'))
            price = parse_amount(c.get('price'))
            cost = round(qty * price, 2)

        if vat == 0 and str(c.get('vat_rate', '')).strip() == '20%':
            vat = round(cost * 0.20, 2)
        if with_vat == 0:
            with_vat = round(cost + vat, 2)

        total_cost += cost
        total_vat += vat
        total_with_vat += with_vat

    return (round(total_cost, 2), round(total_vat, 2),
            round(total_with_vat, 2))


def amount_to_words_parts(amount):
    """Возвращает сумму прописью и копейки: (рубли словами, '00').

    Например, 350.40 -> ('триста пятьдесят', '40').
    Для нулевой суммы возвращает две пустые строки: если стоимость
    в заявке не рассчитывается, поля копеек тоже должны оставаться пустыми.
    """
    value = round(parse_amount(amount), 2)
    if value <= 0:
        return '', ''

    rubles = int(value)
    kopecks = int(round((value - rubles) * 100))
    if kopecks >= 100:
        rubles += kopecks // 100
        kopecks %= 100

    return number_to_text(str(rubles)), f"{kopecks:02d}"


def _places_words(number):
    """Число мест прописью с нейтральным окончанием: одно, два, двадцать одно."""
    number = int(number)
    if number == 0:
        return 'ноль'
    text = _int_to_words(number)
    if number % 10 == 1 and number % 100 != 11 and text.endswith('один'):
        text = text[:-4] + 'одно'
    return text


def places_to_text(places_str):
    p = str(places_str).strip().lower().replace('.', '')
    if not p:
        return ''
    if p in ('нав', 'навал'):
        return 'навал'
    try:
        num = int(p)
    except ValueError:
        return str(places_str)
    return _places_words(num)


def is_tipper_cargo(cargo):
    """Признак груза самосвала: в нём указано число рейсов."""
    return bool(str((cargo or {}).get('trips', '') or '').strip())


def cargo_places_value(cargo):
    """Места для документов: явное значение или «нав.» у самосвала."""
    places = str((cargo or {}).get('places', '') or '').strip()
    if places:
        return places
    return 'нав.' if is_tipper_cargo(cargo) else ''


def calculate_total_places_text_master(cargos):
    has_nav = False
    numbers = []
    for c in cargos:
        p = str(c.get('places', '')).strip().lower().replace('.', '')
        if not p and is_tipper_cargo(c):
            p = 'нав'
        if not p:
            continue
        if p in ('нав', 'навал'):
            has_nav = True
        else:
            try:
                numbers.append(int(p))
            except ValueError:
                pass
    if has_nav:
        return 'навал'
    if numbers:
        return places_to_text(str(sum(numbers)))
    return ''


def strip_driver_prefix(name):
    name = (name or '').strip()
    if name.lower().startswith('водитель'):
        name = name[len('водитель'):].strip()
    return name


def status_ru(status):
    return {'new': '🆕 Новая', 'confirmed': '✅ Подтверждена',
            'printed': '🖨 Распечатана', 'archived': '📦 В архиве',
            'deleted': '🗑 Удалена'}.get(status, f'❔ {status}')


def delivery_status_ru(status):
    """Человекочитаемый статус доставки заявки мастеру."""
    return {
        'delivered': '✅ доставлено мастеру',
        'failed': '❌ не доставлено',
        'pending': '⏳ ожидает отправки',
        'unknown': '—',
    }.get(status or 'unknown', f'❔ {status}')


def find_masters_by_loading(loading_name):
    loc_id = None
    for l_id, l_info in LOCATIONS.items():
        if l_info['name'] == loading_name:
            loc_id = l_id
            break
    if not loc_id:
        return [YOUR_TELEGRAM_ID]
    master_ids = []
    for m_id, m_info in MASTERS.items():
        try:
            m_id_int = int(m_id)
        except (ValueError, TypeError):
            continue
        if loc_id in m_info.get('locations', []):
            master_ids.append(m_id_int)
    if not master_ids:
        master_ids = [YOUR_TELEGRAM_ID]
    return master_ids
# =============================================================
# ТЕСТ ГЕНЕРАЦИИ ТТН (Без запуска бота)
# =============================================================
import os
from word_filler import fill_documents, convert_to_pdf


def generate_test(count):
    print(f"\n⏳ Генерирую ТТН с {count} грузами...")

    # Создаем фейковый список грузов
    cargos = []
    for i in range(1, count + 1):
        cargos.append({
            'cargo_name': f'Тестовый груз №{i} (длинное название для проверки переноса)',
            'si': 'тн',
            'unit': f'{10 + i}',
            'cargo_qty': f'{(10 + i) * 1.5:.2f}'.replace('.', ','),
            'price': '15,00',
            'total_cost': f'{(10 + i) * 15:.2f}'.replace('.', ','),
            'vat_rate': '20',
            'vat_cost': f'{(10 + i) * 15 * 0.2:.2f}'.replace('.', ','),
            'total_with_vat': f'{(10 + i) * 15 * 1.2:.2f}'.replace('.', ','),
            'places': str(i * 2)
        })

    # Фейковые данные заявки
    data = {
        'waybill_number': '123456',
        'day': '21', 'month': '10', 'year': '26',
        'car_model': 'МАЗ 6501С5', 'car_plate': 'А000АА-0',
        'trailer_info': 'Прицеп-платформа',
        'driver_name': 'Иванов И.И.',
        'customer': 'ООО «Демо-Строй»',
        'shipper': 'ООО «Демо-Строй»',
        'consignee': 'ООО «Демо-Строй»',
        'release_basis': 'Распоряжение №15',
        'loading_point': 'Площадка №1',
        'unloading_point': 'Объект «Школа»',
        'total_mass_text': 'Сто целых ноль десятых тонн',
        'total_places_text': 'двадцать',
        'total_vat_text': 'Триста пятьдесят',
        'total_vat_cents': '40',
        'total_with_vat_text': 'Две тысячи сто два',
        'total_with_vat_cents': '40',
        'release_allowed_by': 'Директор',
        'shipper_handed_by': 'Мастер',
        'consignee_received_by': 'Прораб',
        'cargos': cargos
    }

    # Запускаем наш заполнитель
    docx_path, _, _ = fill_documents(data, f"Тест_{count}_грузов")

    # Конвертируем в PDF
    success, pdf_path = convert_to_pdf(docx_path)
    if success:
        print(f"✅ Успешно создан файл: {pdf_path}")
    else:
        print(f"❌ Ошибка конвертации: {pdf_path}")


if __name__ == "__main__":
    # Тестируем разные варианты
    generate_test(1)  # 1 груз
    generate_test(5)  # 5 грузов
    generate_test(10)  # 10 грузов (проверка уменьшения шрифта)
from openai import OpenAI
import base64
import json
import os

# ==========================================
# НАСТРОЙКИ ПОДКЛЮЧЕНИЯ К AIAI.BY
# ==========================================
# Ключ хранится только в переменной окружения. Не коммитьте его в код.
API_KEY = os.environ.get("AIAI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "Не задан AIAI_API_KEY. Установите переменную окружения с ключом AIAI.BY."
    )

client = OpenAI(
    base_url="https://api.aiai.by/v1",   # <--- ВОТ ЭТА СТРОКА ОТВЕЧАЕТ ЗА ХОСТИНГ
    api_key=API_KEY
)

# ==========================================
# ПУТЬ К ТЕСТОВОМУ ФОТО
# ==========================================
# Положите фото путевого листа в папку "Путевые" и назовите его "тест.jpg"
image_path = "Путевые/тест.jpg"

# ==========================================
# ОТПРАВКА ЗАПРОСА
# ==========================================
with open(image_path, "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

print("Отправляю фото в ИИ...")

response = client.chat.completions.create(
    model="gpt-4o",  # Модель, которая умеет смотреть картинки
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": """
                Ты — ассистент мастера стройки. Это документ от организации ООО «Демо-Строй». ВСЕГДА используй полное название «ООО «Демо-Строй»» для полей customer, shipper, consignee. НИКОГДА не добавляй слово «Филиал». Обрати особое внимание на год: в путевом листе указываются только последние две цифры текущего года (например, «26» означает 2026 год). :
                {
                    "waybill_number": "номер путевого листа",
                    "day": "день",
                    "month": "месяц"
                    "year": "год"
                    "car_model": "марка авто",
                    "car_plate": "гос номер авто",
                    "trailer_info": "информация про прицеп или -",
                    "driver_name": "ФИО водителя",
                    "customer": "заказчик или ООО «Демо-Строй»",
                    "shipper": "грузоотправитель или ООО «Демо-Строй»",
                    "consignee": "грузополучатель или ООО «Демо-Строй»",
                    "release_basis": "основание отпуска или Распоряжение директора",
                    "loading_point": "пункт погрузки",
                    "unloading_point": "пункт разгрузки",
                    "cargo_name": "наименование груза",
                    "unit": "ед. измерения",
                    "qty": "количество"
                }"""
                },
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }
    ],
    max_tokens=1000
)

# ==========================================
# ВЫВОД РЕЗУЛЬТАТА
# ==========================================
result = response.choices[0].message.content
print("\nОтвет от ИИ:")
print(result)

# Пробуем превратить ответ в словарь Python
try:
    data = json.loads(result)
    print("\n✅ Распознанные данные:")
    for key, value in data.items():
        print(f"  {key}: {value}")
except json.JSONDecodeError:
    print("\n❌ Ошибка: ИИ вернул не JSON. Проверьте промпт.")

import re
import os
import requests
import aiohttp
import asyncio
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events

# === Flask-приложение ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Кастинг-бот жив. Бдит кастинги. Не мешай."

# === Загрузка переменных окружения ===
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')
bot_token = os.getenv('BOT_TOKEN')
chat_id = int(os.getenv('CHAT_ID'))

openai_api_key = os.getenv('OPENAI_API_KEY')

b2_key_id = os.getenv('B2_KEY_ID')
b2_app_key = os.getenv('B2_APPLICATION_KEY')
bucket_name = os.getenv('BUCKET_NAME')
session_file_name = os.getenv('SESSION_FILE_NAME', 'session.session')

channels = os.getenv('CHANNELS', '')
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
session_local_path = session_file_name

# === Загрузка .session из B2 (если нет локально) ===
def download_session_from_b2():
    print("Сессионный файл не найден локально. Пытаемся скачать из B2...")
    auth = requests.get(
        "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
        auth=(b2_key_id, b2_app_key)
    )
    if auth.status_code != 200:
        raise RuntimeError(f"Ошибка авторизации B2: {auth.status_code} - {auth.text}")

    auth_data = auth.json()
    download_url = auth_data['downloadUrl']
    auth_token = auth_data['authorizationToken']

    file_url = f"{download_url}/file/{bucket_name}/{session_file_name}"
    headers = {"Authorization": auth_token}
    response = requests.get(file_url, headers=headers)

    if response.status_code == 200:
        with open(session_local_path, 'wb') as f:
            f.write(response.content)
        print("Сессия успешно загружена.")
    else:
        raise RuntimeError(f"Не удалось скачать файл из B2: {response.status_code} - {response.text}")

if not os.path.exists(session_local_path):
    download_session_from_b2()
else:
    print("Сессия найдена локально. Используем её.")

# === Инициализация Telegram клиента ===
client = TelegramClient(session_local_path, api_id, api_hash)

# === Проверка релевантности сообщения локально ===
def is_relevant_message(text):
    text = text.lower()

    age_match = re.search(r'(?:возраст[\s:–\-]*)?(?:от)?\s*(\d{2})[\s\-–~]{0,3}(?:до)?\s*(\d{2})?\s*лет', text)
    if age_match:
        age_start = int(age_match.group(1))
        age_end = int(age_match.group(2)) if age_match.group(2) else age_start
        if age_end < 30 or age_start > 50:
            return False
    else:
        return False

    if 'женщин' in text or 'девушк' in text:
        return False

    role_keywords = ['роль', 'играет', 'персонаж', 'герой', 'типаж']
    if not any(kw in text for kw in role_keywords):
        return False

    return True

# === GPT-фильтрация ===
async def is_relevant_by_gpt(text):
    import openai
    openai.api_key = openai_api_key

    prompt = f"""
Ты — эксперт-аналитик по кастингам с огромным опытом, который не просто читает объявления, а буквально вчитывается в каждое слово, чтобы понять, подходит ли мужчина 43 лет для участия.

Задача: оценить, подходит ли кастинг по профессии для мужчины 43 лет, который ищет серьёзную работу в кино, рекламе, озвучке, короткометражках и эпизодах, включая проекты с оплатой и без, но с творческим смыслом.

---

### ВАЖНО — ТРЁХСТУПЕНЧАТЫЙ ФИЛЬТР

1. **Отсеивать массовки, групповые сцены (АМС), тусовочные мероприятия, семинары, кастинги для ассистентов режиссёра или технического персонала.** Это для того, чтобы пользователь не терял время на неактуальные объявления.

2. **Фокусироваться на возрасте 30-50 лет (особенно 40+), пол — мужчина, с возможным расширением, если указано «любой пол» или «мужчина/женщина».**

3. **Учитывать формат и характер проекта — кино, реклама, озвучка, короткометражки, серьёзные эпизоды. Оценивать качество предложения: оплачиваемый, перспективный, творчески интересный.**

---

### АНАЛИЗ — НА ЧТО ОБРАЩАТЬ ВНИМАНИЕ

- Возраст, пол, требования к внешности и опыту
- Формулировки, которые могут означать массовку, техническую роль или тусовку
- Условия оплаты (оплата, гонорар, работа бесплатно, обмен опытом)
- Тон и стиль объявления — есть ли намёк на серьёзность или это шуточное/неформальное предложение
- Контекст локации и возможные ограничения
- Наличие ключевых слов: «технический персонал», «ассистент», «массовка», «семинар», «съёмки групповые», «без опыта», «обмен опытом»

---

### ФОРМАТ ОТВЕТА (ОДИН ИЗ ТРЁХ)

YES: Кастинг подходит. Приведи аргументы, почему — по возрасту, по формату, условиям.

NO: Кастинг не подходит. Укажи конкретные причины — массовка, пол, возраст, формат, непрофессиональный уровень.

MAYBE: Нужна дополнительная информация или сомнения из-за неясности формулировок.

---

### ПРИМЕРЫ СЛОЖНЫХ СИТУАЦИЙ

YES: Ищут мужчину 40-50 лет для эпизода в короткометражном фильме, оплата предусмотрена, опыт не обязателен, формат — серьёзный художественный проект.

NO: Объявление на массовку с 20-30 людьми без указания ролей, «ищем ассистентов и массовку», без оплаты, больше похоже на тусовку.

MAYBE: Нет указания возраста, упоминается «работа для творческих людей», возможно подходит, но нужно уточнять.

---

### ТЕКСТ ОБЪЯВЛЕНИЯ:

{text}

---

### ОТВЕТ:
"""

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты эксперт по кастингам для мужчин 40+."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
        )
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "MAYBE: Ошибка при анализе с GPT."

# === Обработчик новых сообщений в Telegram ===
@client.on(events.NewMessage(chats=channels_list))
async def handler(event):
    text = event.message.message
    if not text:
        return

    # Локальная фильтрация
    if not is_relevant_message(text):
        return

    # GPT-фильтрация
    result = await is_relevant_by_gpt(text)
    print(f"GPT фильтр вернул:\n{result}\n")

    # По желанию — отправить в телегу или куда надо
    if result.startswith("YES"):
        await client.send_message(chat_id, f"Подходит кастинг:\n\n{text}\n\nРешение:\n{result}")

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def run_telegram():
    client.start()
    print("Telegram client запущен.")
    client.run_until_disconnected()

if __name__ == "__main__":
    Thread(target=run_flask).start()
    run_telegram()

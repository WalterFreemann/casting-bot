import re
from telethon import TelegramClient, events
import asyncio
import aiohttp
import os
import requests
from flask import Flask
from threading import Thread

# === Flask-приложение для Render ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Кастинг-бот жив. Бдит кастинги. Не мешай."

# === Загрузка переменных окружения ===
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')

b2_key_id = os.getenv('B2_KEY_ID')
b2_app_key = os.getenv('B2_APPLICATION_KEY')
bucket_name = os.getenv('BUCKET_NAME')
session_file_name = os.getenv('SESSION_FILE_NAME', 'session.session')

channels = os.getenv('CHANNELS', '')
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
session_local_path = session_file_name

# === Загрузка .session из приватного Backblaze B2 ===
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

# === Проверка наличия сессионного файла ===
if not os.path.exists(session_local_path):
    download_session_from_b2()
else:
    print("Сессия найдена локально. Используем её.")

# === Инициализация Telegram клиента ===
client = TelegramClient(session_local_path, api_id, api_hash)

# === Функция проверки релевантности сообщения ===
def is_relevant_message(text):
    age_patterns = [
        r'\b(?:3[0-9]|4[0-9]|50)[\s\-–~]{0,3}лет',
        r'\bвозраст\s*[—\-]?\s*(?:3[0-9]|4[0-9]|50)'
    ]
    male_keywords = ['мужчина', 'парень', 'мужская роль', 'типаж мужчины', 'герой-мужчина']
    role_keywords = ['роль', 'играет', 'персонаж', 'герой']

    text_lower = text.lower()
    has_age = any(re.search(p, text_lower) for p in age_patterns)
    has_male = any(kw in text_lower for kw in male_keywords)
    has_role = any(kw in text_lower for kw in role_keywords)

    return has_age and (has_male or has_role)

# === Отправка сообщения в Telegram ===
async def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()

# === Обработчик новых сообщений ===
@client.on(events.NewMessage(chats=channels_list))
async def handler(event):
    message = event.message.message
    if is_relevant_message(message):
        chat_title = event.chat.title if event.chat else 'Без имени'
        short_message = message[:500] + ('...' if len(message) > 500 else '')
        info = f"Нашёл кастинг: {chat_title}\n{short_message}"
        print(info)
        await send_telegram_message(info)
    else:
        print(f"[Пропущено] {event.chat.title if event.chat else 'Без имени'}")

# === Проверка подключения к каналам ===
async def check_channels():
    print("🔍 Проверка подключения к каналам...")
    for ch in channels_list:
        try:
            entity = await client.get_entity(ch)
            title = getattr(entity, 'title', 'Без названия')
            print(f"✅ Подключен к: {ch} — {title}")
        except Exception as e:
            print(f"❌ Ошибка при подключении к {ch}: {e}")

# === Запуск бота в отдельном потоке ===
def start_bot():
    async def main():
        await client.start(phone=phone)
        print("Бот запущен и слушает сообщения...")

        # 👇 Проверка подключений к каналам
        await check_channels()

        await client.run_until_disconnected()

    asyncio.run(main())

# === Стартуем ===
if __name__ == '__main__':
    Thread(target=start_bot).start()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

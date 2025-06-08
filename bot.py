import os
import re
import requests
import asyncio
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

# === Flask-приложение для живучести на Render или других PaaS ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Кастинг-бот жив. Бдит кастинги. Не мешай."

# === Получение переменных окружения с проверками ===
def get_env_var(key, required=True, cast=str, default=None):
    value = os.getenv(key)
    if value is None:
        if required:
            raise RuntimeError(f"⛔ Переменная окружения '{key}' не задана")
        return default
    try:
        return cast(value)
    except Exception as e:
        raise RuntimeError(f"⛔ Ошибка при преобразовании '{key}': {e}")

# === Настройки и переменные ===
api_id = get_env_var('API_ID', cast=int)
api_hash = get_env_var('API_HASH')
phone = get_env_var('PHONE')
bot_token = get_env_var('BOT_TOKEN')
chat_id = get_env_var('CHAT_ID')

b2_key_id = get_env_var('B2_KEY_ID')
b2_app_key = get_env_var('B2_APPLICATION_KEY')
bucket_name = get_env_var('BUCKET_NAME')
session_file_name = get_env_var('SESSION_FILE_NAME', required=False, default='session.session')

channels_raw = get_env_var('CHANNELS', required=False, default='')
channels_list = [c.strip() for c in channels_raw.split(',') if c.strip()]

session_local_path = session_file_name

# === Загрузка сессионного файла из B2, если локально его нет ===
def download_session_from_b2():
    print("Сессионный файл не найден. Скачиваем из Backblaze B2...")

    auth = requests.get(
        "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
        auth=(b2_key_id, b2_app_key)
    )

    if auth.status_code != 200:
        raise RuntimeError(f"B2 авторизация провалилась: {auth.status_code} — {auth.text}")

    data = auth.json()
    file_url = f"{data['downloadUrl']}/file/{bucket_name}/{session_file_name}"
    headers = {"Authorization": data['authorizationToken']}

    response = requests.get(file_url, headers=headers)
    if response.status_code == 200:
        with open(session_local_path, 'wb') as f:
            f.write(response.content)
        print("✅ Сессия загружена успешно.")
    else:
        raise RuntimeError(f"❌ Не удалось скачать .session из B2: {response.status_code} — {response.text}")

if not os.path.exists(session_local_path):
    download_session_from_b2()
else:
    print("✅ Локальная .session найдена. Используем её.")

# === Инициализация клиента ===
client = TelegramClient(session_local_path, api_id, api_hash)

# === Фильтрация сообщений по возрасту, полу и ролям ===
def is_relevant_message(text):
    text_lower = text.lower()
    age_patterns = [
        r'\b(?:3[0-9]|4[0-9]|50)[\s\-–~]{0,3}лет\b',
        r'\bвозраст\s*[—\-]?\s*(?:3[0-9]|4[0-9]|50)'
    ]
    male_keywords = ['мужчина', 'парень', 'мужская роль', 'типаж мужчины', 'герой-мужчина']
    role_keywords = ['роль', 'играет', 'персонаж', 'герой']

    has_age = any(re.search(p, text_lower) for p in age_patterns)
    has_male = any(k in text_lower for k in male_keywords)
    has_role = any(k in text_lower for k in role_keywords)

    return has_age and (has_male or has_role)

# === Отправка сообщений в Telegram (боту) ===
async def send_telegram_message(text):
    try:
        await client.send_message(chat_id, text)
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения: {e}")

# === Обработка новых сообщений ===
@client.on(events.NewMessage(chats=channels_list))
async def handle_message(event):
    text = event.message.message
    if is_relevant_message(text):
        title = event.chat.title if event.chat else 'Без названия'
        snippet = text[:500] + ('...' if len(text) > 500 else '')
        output = f"📢 Кастинг найден: {title}\n{snippet}"
        print(output)
        await send_telegram_message(output)
    else:
        print(f"[Пропуск] {event.chat.title if event.chat else 'Без названия'}")

# === Проверка, подписан ли пользователь на каналы ===
async def check_user_subscriptions():
    print("\n🔍 Проверка подписок пользователя...")
    dialogs = await client.get_dialogs()
    subscribed = [getattr(d.entity, 'username', None) for d in dialogs if d.is_channel]

    for ch in channels_list:
        if ch in subscribed:
            print(f"✅ Подписка есть: {ch}")
        else:
            print(f"❌ Подписки НЕТ: {ch}")

# === Проверка возможности подключения к каналам ===
async def check_channels():
    print("\n🔧 Проверка get_entity() для каналов...")
    for ch in channels_list:
        try:
            entity = await client.get_entity(ch)
            title = getattr(entity, 'title', 'Без названия')
            print(f"✅ Подключен к {ch} — {title}")
        except Exception as e:
            print(f"❌ Ошибка подключения к {ch}: {e}")

# === Запуск Flask в фоне ===
def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# === Главная функция запуска ===
async def main():
    try:
        await client.start(phone=phone)
    except SessionPasswordNeededError:
        print("❌ Требуется 2FA пароль. Добавь поддержку, если нужно.")
        return

    print("🚀 Бот запущен и слушает каналы...")
    await check_user_subscriptions()
    await check_channels()
    await client.run_until_disconnected()

# === Запуск ===
if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())

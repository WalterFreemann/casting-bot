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

b2_key_id = os.getenv('B2_KEY_ID')
b2_app_key = os.getenv('B2_APPLICATION_KEY')
bucket_name = os.getenv('BUCKET_NAME')
session_file_name = os.getenv('SESSION_FILE_NAME', 'session.session')

channels = os.getenv('CHANNELS', '')
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
session_local_path = session_file_name

required_vars = {
    "API_ID": api_id,
    "API_HASH": api_hash,
    "PHONE": phone,
    "BOT_TOKEN": bot_token,
    "CHAT_ID": chat_id,
    "B2_KEY_ID": b2_key_id,
    "B2_APPLICATION_KEY": b2_app_key,
    "BUCKET_NAME": bucket_name
}

for var_name, var_value in required_vars.items():
    if not var_value:
        raise RuntimeError(f"ОШИБКА: Переменная окружения '{var_name}' не задана!")

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

    # Отсекаем женские кастинги
    if 'женщин' in text or 'девушк' in text:
        return False

    # Проверка ключевых слов
    role_keywords = [
        'роль', 'играет', 'персонаж', 'герой', 'типаж', 'проба', 'в кастинг', 'на кастинг',
        'снимается', 'ищем актера', 'ищем артиста', 'сценарий', 'эпизод', 'героиня', 'актёр',
        'второстепенная роль', 'главная роль', 'камео', 'появляется в кадре', 'игровая роль',
        'роль без слов', 'диалог', 'актёр на съёмку', 'мужской образ', 'второй план'
    ]
    if not any(kw in text for kw in role_keywords):
        return False

    # Фильтр по возрасту (более гибкий и защищённый)
    age_match = re.search(r'(?:возраст[\s:–\-]*)?(?:от)?\s*(\d{2})[\s\-–~]{0,3}(?:до)?\s*(\d{2})?\s*лет', text)
    if age_match:
        try:
            age_start = int(age_match.group(1))
            age_end = int(age_match.group(2)) if age_match.group(2) else age_start
            if age_end < 30 or age_start > 50:
                return False
        except ValueError:
            pass  # если парсинг не удался — пропускаем фильтр

    return True

# === Пересылка или копирование сообщения пользователю ===
async def forward_message(event):
    try:
        await client.forward_messages(chat_id, event.message)
        print(f"✅ Переслал сообщение из {event.chat.title if event.chat else 'неизвестного канала'}")

    except Exception as e:
        print(f"⚠️ Не удалось переслать сообщение: {e}")
        msg = event.message
        text = msg.text or msg.caption

        if text:
            print(f"📄 Копирую текст вручную: {text[:50]}...")
            await client.send_message(chat_id, f"📌 Кастинг подходит:\n\n{text}")
        else:
            print("❌ Нет текста для анализа (ни text, ни caption)")

# === Обработчик новых сообщений ===
@client.on(events.NewMessage(chats=channels_list))
async def handler(event):
    msg_text = event.message.message or ''
    if is_relevant_message(msg_text):
        await forward_message(event)
    else:
        print(f"[Пропущено] {event.chat.title if event.chat else 'Без имени'}")

# === Проверка подписок пользователя сессии ===
async def check_user_subscriptions():
    print("\n🔎 Проверяем реальные подписки пользователя сессии...")
    dialogs = await client.get_dialogs()
    channels_user_is_in = []
    for dialog in dialogs:
        if dialog.is_channel:
            username = getattr(dialog.entity, 'username', None)
            if username:
                channels_user_is_in.append(username)
    print(f"Каналы в подписках пользователя: {channels_user_is_in}\n")

    print("Сравнение с твоим списком каналов:")
    for ch in channels_list:
        if ch in channels_user_is_in:
            print(f"✅ {ch} — подписка есть")
        else:
            print(f"❌ {ch} — подписки НЕТ")

# === Проверка подключения к каналам ===
async def check_channels():
    print("\n🔍 Проверка подключения к каналам (get_entity)...")
    for ch in channels_list:
        try:
            entity = await client.get_entity(ch)
            title = getattr(entity, 'title', 'Без названия')
            print(f"✅ Подключен к: {ch} — {title}")
        except Exception as e:
            print(f"❌ Ошибка при подключении к {ch}: {e}")

# === Функция для запуска Flask в отдельном потоке ===
def run_flask():
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# === Основная async функция запуска бота ===
async def main():
    await client.start(phone=phone)
    print("Бот запущен и слушает сообщения...")
    await check_user_subscriptions()
    await check_channels()
    await client.run_until_disconnected()

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    asyncio.run(main())

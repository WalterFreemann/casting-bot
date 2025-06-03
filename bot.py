from telethon import TelegramClient, events
import asyncio
import aiohttp
import os
import requests

# === Загрузка переменных окружения ===
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')  # Можно не указывать, если есть session
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')  # ID или username чата для уведомлений

channels = os.getenv('CHANNELS', '')
keywords = os.getenv('KEYWORDS', '')

# === Преобразование строк в списки ===
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
keywords_list = [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]

# === Путь к локальному сессионному файлу ===
session_local_path = 'session.session'

# === Загрузка .session через HTTP (Backblaze URL из переменной окружения) ===
session_file_url = os.getenv('SESSION_FILE_URL')

if not os.path.exists(session_local_path):
    print("Сессионный файл не найден локально. Скачиваем...")

    if not session_file_url:
        raise ValueError("Не задана переменная окружения SESSION_FILE_URL")

    response = requests.get(session_file_url)
    if response.status_code == 200:
        with open(session_local_path, 'wb') as f:
            f.write(response.content)
        print("Сессия успешно загружена.")
    else:
        raise RuntimeError(f"Не удалось скачать файл: {response.status_code} - {response.text}")
else:
    print("Сессия найдена локально. Используем её.")

# === Инициализация Telegram клиента ===
client = TelegramClient(session_local_path, api_id, api_hash)

# === Функция отправки сообщений в Telegram ===
async def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()

# === Обработчик новых сообщений ===
@client.on(events.NewMessage(chats=channels_list))
async def handler(event):
    message = event.message.message.lower()
    if any(keyword in message for keyword in keywords_list):
        chat_title = event.chat.title if event.chat else 'Без имени'
        info = f"Нашёл кастинг: {chat_title} - {event.message.message}"
        print(info)
        await send_telegram_message(info)

# === Основной цикл ===
async def main():
    await client.start(phone=phone)
    print("Бот запущен и слушает сообщения...")
    await client.run_until_disconnected()

# === Запуск ===
if __name__ == '__main__':
    asyncio.run(main())

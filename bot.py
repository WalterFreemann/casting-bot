from telethon import TelegramClient, events
import asyncio
import aiohttp
import os
import boto3
from botocore.client import Config

# === Загрузка переменных окружения ===
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')  # можно не указывать, если сессия есть
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')  # ID или username чата для уведомлений

channels = os.getenv('CHANNELS', '')
keywords = os.getenv('KEYWORDS', '')

# === Преобразование строк в списки ===
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
keywords_list = [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]

# === Путь к локальному сессионному файлу ===
session_local_path = 'session.session'

# === Загрузка сессии из B2 через S3, если файл не существует ===
if not os.path.exists(session_local_path):
    print("Сессионный файл не найден локально. Скачиваем из B2...")

    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv('S3_KEY_ID'),
        aws_secret_access_key=os.getenv('S3_APPLICATION_KEY'),
        endpoint_url=os.getenv('S3_ENDPOINT'),
        config=Config(signature_version='s3v4')
    )

    s3.download_fileobj(
        os.getenv('S3_BUCKET_NAME'),
        os.getenv('S3_SESSION_FILE'),
        open(session_local_path, 'wb')
    )

    print("Сессия успешно загружена.")
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

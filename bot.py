from telethon import TelegramClient, events
import asyncio
import aiohttp
import os

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')  # можно не указывать, если сессия есть
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')  # сюда пиши, куда слать сообщения от бота

channels = os.getenv('CHANNELS', '')
keywords = os.getenv('KEYWORDS', '')

# Превращаем строки в списки, убираем пустые элементы и пробелы
channels_list = [ch.strip() for ch in channels.split(',') if ch.strip()]
keywords_list = [kw.strip().lower() for kw in keywords.split(',') if kw.strip()]

# Определяем путь к сессионному файлу
session_env_path = '/etc/secrets/session.session'

if os.path.exists(session_env_path):
    session_path = session_env_path
else:
    session_path = f"{os.getenv('SESSION_NAME', 'casting_session')}.session"

client = TelegramClient(session_path, api_id, api_hash)

async def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()

@client.on(events.NewMessage(chats=channels_list))
async def handler(event):
    message = event.message.message.lower()
    if any(keyword in message for keyword in keywords_list):
        chat_title = event.chat.title if event.chat else 'Без имени'
        info = f"Нашёл кастинг: {chat_title} - {event.message.message}"
        print(info)
        await send_telegram_message(info)

async def main():
    await client.start(phone=phone)
    print("Бот запущен и слушает сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())

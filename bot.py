from telethon import TelegramClient, events
import asyncio
import aiohttp
import os

# Переменные из env (Render)
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
phone = os.getenv('PHONE')  # не обязательно, если сессия уже есть
bot_token = os.getenv('BOT_TOKEN')

# Создаём Telethon клиента (юзер-бота)
client = TelegramClient('casting_session', api_id, api_hash)

async def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": YOUR_CHAT_ID,  # сюда свой chat_id поставь, куда хочешь получать сообщения
        "text": text
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()

@client.on(events.NewMessage)
async def handler(event):
    message = event.message.message.lower()
    if 'кастинг' in message:
        chat_title = event.message.chat.title if event.message.chat else 'Без имени'
        info = f"Нашёл кастинг: {chat_title} - {event.message.message}"
        print(info)
        await send_telegram_message(info)

async def main():
    await client.start(phone=phone)
    print("Бот запущен и слушает сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())

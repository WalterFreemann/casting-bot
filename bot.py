from telethon import TelegramClient, events

api_id = YOUR_API_ID
api_hash = 'YOUR_API_HASH'
phone = '+7XXXXXXXXXX'  # твой номер с +7 или другим кодом

client = TelegramClient('session_name', api_id, api_hash)

@client.on(events.NewMessage)
async def handler(event):
    message = event.message.message.lower()
    if 'кастинг' in message:
        print(f"Нашёл кастинг: {event.message.chat.title if event.message.chat else 'Чат без имени'} - {event.message.message}")
        # Здесь можно отправить уведомление себе или записать в базу

async def main():
    await client.start(phone)
    print("Бот запущен и слушает сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())

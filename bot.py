from telethon import TelegramClient, events
import os

api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')

client = TelegramClient('casting_bot', api_id, api_hash).start(bot_token=bot_token)

@client.on(events.NewMessage(pattern='/start'))
async def handler(event):
    await event.respond('Привет! Я кастинг-бот. Пока что умею только приветствовать :)')
    raise events.StopPropagation

print('Бот запущен...')
client.run_until_disconnected()

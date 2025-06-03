import os
import requests
from telethon import TelegramClient

# 🔐 Авторизация в Backblaze B2
def authorize_b2():
    key_id = os.environ['B2_KEY_ID']
    app_key = os.environ['B2_APPLICATION_KEY']
    auth_url = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"
    response = requests.get(auth_url, auth=(key_id, app_key))
    if response.status_code != 200:
        raise RuntimeError(f"Ошибка авторизации B2: {response.status_code} - {response.text}")
    return response.json()

# 📦 Скачивание файла сессии из B2
def download_b2_file(auth_data):
    api_url = auth_data['downloadUrl']
    auth_token = auth_data['authorizationToken']
    bucket = os.environ['B2_BUCKET_NAME']
    file_name = os.environ['B2_FILE_NAME']
    file_url = f"{api_url}/file/{bucket}/{file_name}"

    headers = {"Authorization": auth_token}
    response = requests.get(file_url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Не удалось скачать файл: {response.status_code} - {response.text}")

    with open(file_name, "wb") as f:
        f.write(response.content)
    print(f"✅ Сессионный файл '{file_name}' успешно скачан и сохранён локально.")

# 🚀 Проверка наличия локального сессионного файла
session_file = os.environ.get("B2_FILE_NAME", "session.session")
if not os.path.exists(session_file):
    print("Сессионный файл не найден локально. Скачиваем...")
    auth_data = authorize_b2()
    download_b2_file(auth_data)

# 📱 Запуск бота
api_id = int(os.environ['TG_API_ID'])
api_hash = os.environ['TG_API_HASH']
bot_token = os.environ['TG_BOT_TOKEN']

client = TelegramClient(session_file.replace(".session", ""), api_id, api_hash).start(bot_token=bot_token)

# Простой handler для проверки
@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("Бот успешно запущен и готов к работе!")

print("✅ Бот запущен.")
client.run_until_disconnected()

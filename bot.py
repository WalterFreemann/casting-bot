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
    import re
    text = text.lower()

    # === Этап 0. Явные мусорные фразы (blacklist) ===
    blacklist_phrases = [
        'в рамках марафона', 'прямой эфир', 'вебинар', 'запишитесь на курс',
        'стоимость участия', 'встречаемся в чате', 'выберите тариф', 'занятие будет завтра',
        'лекция', 'обучение', 'бесплатно присоединяйся', 'разборы проб',
        'кастинг-директор поделится опытом', 'для записи пишите', 'занятие по комедии',
        'видеовизитка с режиссером', 'фотодень', 'пакет услуг', 'тариф',
        'визажист', 'в студии', 'брифинг', 'воркшоп', 'подключайтесь к трансляции',
        'обзор проб', 'отзывы участников'
    ]
    for phrase in blacklist_phrases:
        if phrase in text:
            return False

    # === Этап 1. Явно нерелевантное — не кастинг ===
    non_casting_keywords = [
        'мероприятие', 'фуршет', 'презентация', 'зрители', 'официанты', 'гости',
        'в клубе', 'приглашенные', 'офисные сотрудники', 'для массовки', 'публика',
        'диджей', 'ведущий', 'аниматор', 'модель', 'модели', 'статисты', 'набор в студию'
    ]
    if any(word in text for word in non_casting_keywords):
        return False

    # === Этап 2. Женские кастинги ===
    if ('женщин' in text or 'девушк' in text or 'актрис' in text) and not any(m in text for m in ['мужчин', 'мужск', 'мужчина', 'актёр', 'актер']):
        return False

    # === Этап 3. Слишком низкий гонорар за массовку/эпизод без слов ===
    low_paid_roles = ['массовк', 'группов', 'эпизод без слов', 'врачи', 'санитары', 'проходящ', 'официант', 'прохож']
    pay_match = re.search(r'(\d{3,6})\s*(₽|руб|руб\.|р\b)', text)
    if pay_match:
        amount = int(pay_match.group(1))
        if amount < 5000 and any(word in text for word in low_paid_roles):
            return False

    # === Этап 4. Возрастной фильтр (примерно 25–55 лет) ===
    age_match = re.findall(r'(\d{2})\s*[-–~]?\s*(\d{2})?\s*лет', text)
    for match in age_match:
        start = int(match[0])
        end = int(match[1]) if match[1] else start
        if end < 25 or start > 55:
            return False

    # === Этап 5. Жёсткая этника (исключаем если только один типаж и он не твой) ===
    hard_ethnic = ['восточная внешность', 'узбек', 'таджик', 'кавказская внешность', 'негроид', 'афро']
    if any(e in text for e in hard_ethnic):
        if not any(w in text for w in ['славян', 'русск', 'европе', 'мужчина', 'актёр', 'актер']):
            return False

    # === Этап 6. Проверка на признаки годного кастинга ===
    must_have_keywords = [
        'роль', 'персонаж', 'проба', 'кастинг', 'съёмк', 'эпизод', 'типаж', 'самопроба',
        'в кадре', 'актёр', 'актер', 'на роль', 'играет', 'утверждение', 'пробы'
    ]
    if not any(k in text for k in must_have_keywords):
        return False

    # === Этап 7. География: если НЕ Петербург, то нужен высокий гонорар ===
    is_spb = any(city in text for city in ['спб', 'питер', 'санкт-петербург'])
    if not is_spb and pay_match:
        amount = int(pay_match.group(1))
        if amount < 50000:
            return False

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
            # Получаем ссылку на канал, если возможно
            if event.chat:
                username = getattr(event.chat, 'username', None)
                title = getattr(event.chat, 'title', 'неизвестный канал')
                if username:
                    source = f"t.me/{username}"
                elif title:
                    source = f"Канал: {title}"
                else:
                    source = "Источник неизвестен"
            else:
                source = "Источник неизвестен"

            print(f"📄 Копирую текст вручную: {text[:50]}...")
            await client.send_message(chat_id, f"📌 Кастинг подходит ({source}):\n\n{text}")
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

import discord
import aiohttp

# === НАСТРОЙКИ ===
DISCORD_TOKEN = ""
DISCORD_CHANNEL_ID = 1396780864725057649  # ID текстового канала

TELEGRAM_BOT_TOKEN = ""

USE_TOPIC_CHANNEL = False
TOPIC_THREAD_ID = 151051

TELEGRAM_CHAT_ID = "-1002599295144" if USE_TOPIC_CHANNEL else "-1002599295144" #оригинальный канал -1002443978616

# IP -> тип сервиса
SERVICE_BY_IP = {
    "31.57.34.167": "Minecraft сервер",
    "140.235.74.44": "Voice чат сервис",
}
DEFAULT_SERVICE = "Web сайт"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"[✅] Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    lines = ["📩 <b>Новое сообщение из AntiDDOS</b>", ""]

    target_ip = None
    target_service = DEFAULT_SERVICE

    # Сначала собираем информацию о IP (чтобы понимать, какой это сервис)
    for embed in message.embeds:
        for field in embed.fields:
            if "Целевой IP" in field.name:
                target_ip = field.value.strip()
                target_service = SERVICE_BY_IP.get(target_ip, DEFAULT_SERVICE)
                break
        if target_ip:
            break

    # Затем формируем сообщение
    for embed in message.embeds:
        if embed.title:
            title = embed.title.strip()
            icon = "" if "начал" in title.lower() else ""
            lines.append(f"{icon} <b>{html_escape(title)}</b>\n")

        for field in embed.fields:
            name = field.name.strip()
            value = field.value.strip()

            if any(skip in name for skip in ["Время начала", "Время окончания", "UUID атаки"]):
                continue

            if "Целевой IP" in name:
                lines.append(f"<b>🎯 Целевой сервис:</b> {html_escape(target_service)}")
                # при желании можно добавить сам IP:
                # lines.append(f"<b>🌐 IP:</b> {html_escape(target_ip or value)}")
            elif "Пиковая пропускная способность атаки" in name:
                lines.append(f"<b>📶 Пропускная способность:</b> {html_escape(value)}")
            elif "Пиковое количество пакетов в секунду" in name:
                lines.append(f"<b>📦 Пакеты в секунду:</b> {html_escape(value)}")
            elif "Всего байт отброшено" in name:
                lines.append(f"<b>💾 Байт отброшено:</b> {html_escape(value)}")
            elif "Всего пакетов отброшено" in name:
                lines.append(f"<b>📦 Пакетов отброшено:</b> {html_escape(value)}")

    final_text = "\n".join(lines)
    await send_to_telegram(final_text)


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


async def send_to_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    if USE_TOPIC_CHANNEL:
        payload["message_thread_id"] = TOPIC_THREAD_ID

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            if resp.status == 200:
                print("[➡️] Отправлено в Telegram")
            else:
                print(f"[⚠️] Ошибка Telegram: {resp.status}")
                print(await resp.text())


# Запуск
client.run(DISCORD_TOKEN)


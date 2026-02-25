import discord
import aiohttp
import json
import os
from datetime import datetime, timezone

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
ATTACK_STATE_FILE = "attack_state.json"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


def load_attack_state() -> dict:
    if not os.path.exists(ATTACK_STATE_FILE):
        return {}

    try:
        with open(ATTACK_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_attack_state(state: dict):
    with open(ATTACK_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


attack_state = load_attack_state()


@client.event
async def on_ready():
    print(f"[✅] Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if message.channel.id != DISCORD_CHANNEL_ID:
        return

    for embed in message.embeds:
        event = extract_attack_event(embed)
        if not event:
            continue

        await process_attack_event(event)


def parse_attack_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None

    now_utc = datetime.now(timezone.utc)
    formats = [
        "%m/%d %I:%M:%S%p '%y %z",
        "%m/%d/%I.%M.%S%p %z",
        "%m/%d/%Y %I:%M:%S%p %z",
        "%m/%d/%Y/%I.%M.%S%p %z",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            if "%Y" not in fmt and "'%y" not in fmt:
                parsed = parsed.replace(year=now_utc.year)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def format_duration(start: datetime | None, end: datetime | None) -> str | None:
    if not start or not end or end < start:
        return None

    total_seconds = int((end - start).total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    if seconds or not parts:
        parts.append(f"{seconds}с")
    return " ".join(parts)


def extract_attack_event(embed: discord.Embed) -> dict | None:
    if not embed.title:
        return None

    title = embed.title.strip()
    lowered_title = title.lower()

    event_type = None
    if "начал" in lowered_title:
        event_type = "start"
    elif "заверш" in lowered_title:
        event_type = "end"
    else:
        return None

    data = {
        "event_type": event_type,
        "title": title,
        "target_ip": None,
        "peak_bw": None,
        "peak_pps": None,
        "dropped_bytes": None,
        "dropped_packets": None,
        "attack_uuid": None,
        "start_time": None,
        "end_time": None,
    }

    for field in embed.fields:
        name = field.name.strip()
        value = field.value.strip()
        lowered = name.lower()

        if "целевой ip" in lowered:
            data["target_ip"] = value
        elif "пиковая пропускная способность атаки" in lowered:
            data["peak_bw"] = value
        elif "пиковое количество пакетов в секунду" in lowered:
            data["peak_pps"] = value
        elif "всего байт отброшено" in lowered:
            data["dropped_bytes"] = value
        elif "всего пакетов отброшено" in lowered:
            data["dropped_packets"] = value
        elif "uuid атаки" in lowered:
            data["attack_uuid"] = value
        elif "время начала" in lowered:
            data["start_time"] = parse_attack_datetime(value)
        elif "время окончания" in lowered:
            data["end_time"] = parse_attack_datetime(value)

    return data


def build_telegram_text(event: dict, resolved_title: str, duration: str | None = None) -> str:
    target_service = SERVICE_BY_IP.get(event.get("target_ip"), DEFAULT_SERVICE)
    lines = ["📩 <b>Сообщение из AntiDDOS</b>", "", f"<b>{html_escape(resolved_title)}</b>", ""]

    lines.append(f"<b>🎯 Целевой сервис:</b> {html_escape(target_service)}")

    if event.get("peak_bw"):
        lines.append(f"<b>📶 Пропускная способность:</b> {html_escape(event['peak_bw'])}")
    if event.get("peak_pps"):
        lines.append(f"<b>📦 Пакеты в секунду:</b> {html_escape(event['peak_pps'])}")
    if event.get("dropped_bytes"):
        lines.append(f"<b>💾 Байт отброшено:</b> {html_escape(event['dropped_bytes'])}")
    if event.get("dropped_packets"):
        lines.append(f"<b>📦 Пакетов отброшено:</b> {html_escape(event['dropped_packets'])}")
    if duration:
        lines.append(f"<b>⏳ Длительность атаки:</b> {html_escape(duration)}")

    return "\n".join(lines)


async def process_attack_event(event: dict):
    attack_uuid = event.get("attack_uuid")
    if not attack_uuid:
        text = build_telegram_text(event, event["title"])
        await send_to_telegram(text)
        return

    if event["event_type"] == "start":
        text = build_telegram_text(event, event["title"])
        message_id = await send_to_telegram(text)
        if message_id:
            attack_state[attack_uuid] = {
                "telegram_message_id": message_id,
                "start_time": event["start_time"].isoformat() if event["start_time"] else None,
            }
            save_attack_state(attack_state)
        return

    state = attack_state.get(attack_uuid)
    start_dt = event["start_time"]
    if not start_dt and state and state.get("start_time"):
        try:
            start_dt = datetime.fromisoformat(state["start_time"])
        except ValueError:
            start_dt = None

    duration = format_duration(start_dt, event.get("end_time"))
    end_title = "✅ Атака завершена"
    text = build_telegram_text(event, end_title, duration=duration)

    edited = False
    if state and state.get("telegram_message_id"):
        edited = await edit_telegram_message(state["telegram_message_id"], text)

    if not edited:
        await send_to_telegram(text)

    if attack_uuid in attack_state:
        del attack_state[attack_uuid]
        save_attack_state(attack_state)


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
                response_json = await resp.json()
                return response_json.get("result", {}).get("message_id")
            else:
                print(f"[⚠️] Ошибка Telegram: {resp.status}")
                print(await resp.text())
                return None


async def edit_telegram_message(message_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            if resp.status == 200:
                print(f"[✏️] Обновлено сообщение Telegram #{message_id}")
                return True

            print(f"[⚠️] Ошибка редактирования Telegram: {resp.status}")
            print(await resp.text())
            return False


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)


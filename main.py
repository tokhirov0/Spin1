import os
import random
import json
import telebot
from flask import Flask, request
from dotenv import load_dotenv
from datetime import date
import sqlite3
import logging
import requests

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .env faylidan o‘zgaruvchilarni yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_URL") + "/" + BOT_TOKEN
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Telegram bot va Flask ilovasini ishga tushirish
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# SQLite ma’lumotlar bazasi
DB_FILE = "bot_data.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            user_id INTEGER PRIMARY KEY,
                            balance INTEGER DEFAULT 0,
                            last_bonus_date TEXT
                        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS referrals (
                            user_id INTEGER,
                            referred_id INTEGER,
                            PRIMARY KEY (user_id, referred_id)
                        )''')
        conn.commit()

init_db()

# Kanallar ro‘yxati
CHANNELS_FILE = "channels.json"

def load_channels():
    try:
        if os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Kanal faylini yuklashda xato: {e}")
        return []

def save_channels(channels):
    try:
        with open(CHANNELS_FILE, "w") as f:
            json.dump(channels, f)
    except Exception as e:
        logger.error(f"Kanal faylini saqlashda xato: {e}")

channels = load_channels()

# Foydalanuvchi ma’lumotlarini bazadan olish
def get_user_balance(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

def update_user_balance(user_id, amount):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)",
                      (user_id, amount))
        conn.commit()

def get_last_bonus_date(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_bonus_date FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def update_last_bonus_date(user_id, bonus_date):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_bonus_date = ? WHERE user_id = ?",
                      (bonus_date, user_id))
        conn.commit()

# --- Start ---
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    # Kanal tekshirish
    if channels:
        not_subscribed = []
        for ch in channels:
            try:
                status = bot.get_chat_member(ch, user_id).status
                if status in ["left", "kicked"]:
                    not_subscribed.append(ch)
            except Exception as e:
                logger.error(f"Kanal tekshirishda xato ({ch}): {e}")
                not_subscribed.append(ch)

        if not_subscribed:
            keyboard = telebot.types.InlineKeyboardMarkup()
            for ch in not_subscribed:
                keyboard.add(telebot.types.InlineKeyboardButton("Obuna bo‘lish", url=f"https://t.me/{ch[1:]}"))
            bot.send_message(user_id, "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling:", reply_markup=keyboard)
            return

    # Yangi foydalanuvchi qo‘shish
    if not get_user_balance(user_id):
        update_user_balance(user_id, 0)
        # Referal bonus
        if referrer_id and referrer_id != user_id:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO referrals (user_id, referred_id) VALUES (?, ?)",
                              (referrer_id, user_id))
                conn.commit()
            referrer_balance = get_user_balance(referrer_id)
            update_user_balance(referrer_id, referrer_balance + 2000)
            bot.send_message(referrer_id, f"🎉 Do‘stingiz botga qo‘shildi! Sizga 2000 so‘m bonus qo‘shildi.")

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎰 Spin", "🎁 Bonus", "👤 Profil")
    keyboard.add("💸 Pul yechish", "👥 Referal")
    if user_id == ADMIN_ID:
        keyboard.add("⚙️ Admin panel")

    bot.send_message(user_id, "Salom! Botga xush kelibsiz 👋", reply_markup=keyboard)

# --- Spin ---
@bot.message_handler(func=lambda m: m.text == "🎰 Spin")
def spin_game(message):
    user_id = message.from_user.id
    # GIF URL dan yuborish
    gif_url = "https://media.giphy.com/media/3o6Zta2Xv3d0Xv4zC/giphy.gif"  # Slot machine GIF
    try:
        bot.send_animation(user_id, gif_url, caption="🎰 Baraban aylanmoqda...")
    except Exception as e:
        logger.error(f"GIF yuborishda xato: {e}")
        bot.send_message(user_id, "❌ Texnik xato, keyinroq urinib ko‘ring.")
        return

    reward = random.choices([0, 1000, 2000, 5000, 10000], weights=[0.5, 0.3, 0.15, 0.05, 0.01])[0]
    current_balance = get_user_balance(user_id)
    update_user_balance(user_id, current_balance + reward)
    bot.send_message(user_id, f"✅ Siz {reward} so‘m yutdingiz!\n💰 Balansingiz: {current_balance + reward} so‘m")
    logger.info(f"Foydalanuvchi {user_id} spin o‘ynadi, yutuq: {reward}")

# --- Bonus ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def daily(message):
    user_id = message.from_user.id
    today = str(date.today())
    last_bonus_date = get_last_bonus_date(user_id)

    if last_bonus_date == today:
        bot.send_message(user_id, "❌ Siz bonusni bugun oldingiz, ertaga yana urinib ko‘ring.")
        return

    current_balance = get_user_balance(user_id)
    update_user_balance(user_id, current_balance + 5000)
    update_last_bonus_date(user_id, today)
    bot.send_message(user_id, f"🎁 Sizga 5000 so‘m bonus qo‘shildi!\n💰 Balans: {current_balance + 5000}")
    logger.info(f"Foydalanuvchi {user_id} kunlik bonus oldi")

# --- Profil ---
@bot.message_handler(func=lambda m: m.text == "👤 Profil")
def profile(message):
    user_id = message.from_user.id
    balance = get_user_balance(user_id)
    bot.send_message(user_id, f"👤 ID: <code>{user_id}</code>\n💰 Balans: {balance} so‘m")

# --- Pul yechish ---
@bot.message_handler(func=lambda m: m.text == "💸 Pul yechish")
def withdraw(message):
    msg = bot.send_message(message.chat.id, "💸 Yechmoqchi bo‘lgan summani yozing (100000 so‘mdan kam emas):")
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    user_id = message.from_user.id
    try:
        amount = int(message.text)
    except ValueError:
        bot.send_message(user_id, "❌ Raqam kiriting!")
        return

    if amount < 100000:
        bot.send_message(user_id, "❌ Minimal pul yechish 100000 so‘m.")
        return

    current_balance = get_user_balance(user_id)
    if current_balance < amount:
        bot.send_message(user_id, "❌ Balansingizda mablag‘ yetarli emas.")
        return

    update_user_balance(user_id, current_balance - amount)
    bot.send_message(user_id, f"✅ Pul yechish so‘rovi yuborildi.\n💸 Summasi: {amount} so‘m")
    bot.send_message(ADMIN_ID, f"💸 Yangi pul yechish so‘rovi!\n👤 ID: {user_id}\n💰 Summasi: {amount} so‘m")
    logger.info(f"Foydalanuvchi {user_id} {amount} so‘m yechish so‘rovini yubordi")

# --- Referal ---
@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def referal(message):
    user_id = message.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE user_id = ?", (user_id,))
        referral_count = cursor.fetchone()[0]
    bot.send_message(user_id, f"👥 Do‘stlaringizni taklif qiling!\nReferal linkingiz: {link}\nTaklif qilinganlar: {referral_count}")

# --- Admin panel ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin panel" and m.from_user.id == ADMIN_ID)
def admin_panel(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("➕ Kanal qo‘shish", "➖ Kanal o‘chirish")
    keyboard.add("📊 Statistika", "⬅️ Orqaga")
    bot.send_message(ADMIN_ID, "⚙️ Admin panelga xush kelibsiz!", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "➕ Kanal qo‘shish" and m.from_user.id == ADMIN_ID)
def add_channel(message):
    msg = bot.send_message(ADMIN_ID, "➕ Kanal username-ni kiriting (@ bilan):")
    bot.register_next_step_handler(msg, save_channel)

def save_channel(message):
    ch = message.text.strip()
    if not ch.startswith("@"):
        bot.send_message(ADMIN_ID, "❌ To‘g‘ri formatda kiriting! (@kanal)")
        return
    channels.append(ch)
    save_channels(channels)
    bot.send_message(ADMIN_ID, f"✅ Kanal qo‘shildi: {ch}")
    logger.info(f"Admin kanal qo‘shdi: {ch}")

@bot.message_handler(func=lambda m: m.text == "➖ Kanal o‘chirish" and m.from_user.id == ADMIN_ID)
def del_channel(message):
    if not channels:
        bot.send_message(ADMIN_ID, "❌ Hozircha kanal yo‘q.")
        return
    ch = channels.pop()
    save_channels(channels)
    bot.send_message(ADMIN_ID, f"❌ Kanal o‘chirildi: {ch}")
    logger.info(f"Admin kanal o‘chirdi: {ch}")

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.from_user.id == ADMIN_ID)
def stats(message):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
    bot.send_message(ADMIN_ID, f"📊 Foydalanuvchilar soni: {user_count} ta\n📢 Kanallar: {', '.join(channels) if channels else 'yo‘q'}")
    logger.info("Admin statistikani ko‘rdi")

# --- Orqaga ---
@bot.message_handler(func=lambda m: m.text == "⬅️ Orqaga" and m.from_user.id == ADMIN_ID)
def back(message):
    start(message)

# --- Flask webhook ---
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    try:
        json_str = request.stream.read().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "!", 200
    except Exception as e:
        logger.error(f"Webhook xatosi: {e}")
        return "Error", 500

@app.route("/")
def index():
    return "Bot ishlayapti!", 200

def set_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook o‘rnatildi: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Webhook o‘rnatishda xato: {e}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

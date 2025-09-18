import os
import random
import json
import telebot
from flask import Flask, request
from dotenv import load_dotenv
import logging

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# .env faylidan o‘zgaruvchilarni yuklash
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN topilmadi!")
    exit(1)
WEBHOOK_URL = os.getenv("RENDER_URL") + "/" + BOT_TOKEN
ADMIN_ID = os.getenv("ADMIN_ID")
PORT = int(os.getenv("PORT", 10000))

# Bot va Flask ilovasini ishga tushirish
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Foydalanuvchilar va kanallar fayllarini yuklash
try:
    with open("users.json", "r") as f:
        users = json.load(f)  # {user_id: {"balance": 0, "spins": 0, "referred_by": None}}
except (FileNotFoundError, json.JSONDecodeError):
    users = {}
    logger.info("users.json yaratildi yoki bo'sh bo'lib yuklandi.")

try:
    with open("channels.json", "r") as f:
        channels = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    channels = []
    logger.info("channels.json yaratildi yoki bo'sh bo'lib yuklandi.")

# Ma'lumotlarni saqlash funksiyasi
def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f)
    logger.info("%s saqlandi: %s", file, data)

# /start buyrug'i uchun handler (referral bilan)
@bot.message_handler(commands=['start'])
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

    # Referral bonus
    if referrer_id and referrer_id != user_id:
        referrer_spins = users.get(str(referrer_id), {}).get("spins", 0)
        users[str(referrer_id)] = {"balance": users.get(str(referrer_id), {}).get("balance", 0), "spins": referrer_spins + 1, "referred_by": None}
        save_data("users.json", users)
        bot.send_message(referrer_id, f"🎉 Do‘stingiz botga qo‘shildi! Sizga 1 ta spin qo‘shildi.")

    # Yangi foydalanuvchi qo‘shish
    if str(user_id) not in users:
        users[str(user_id)] = {"balance": 0, "spins": 0, "referred_by": referrer_id}
        save_data("users.json", users)

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎰 Spin", "🎁 Bonus", "👤 Profil")
    keyboard.add("💸 Pul yechish", "👥 Referal")
    if user_id == int(ADMIN_ID):
        keyboard.add("⚙️ Admin panel")

    bot.send_message(user_id, "Salom! Botga xush kelibsiz 👋", reply_markup=keyboard)

# --- Spin ---
@bot.message_handler(func=lambda m: m.text == "🎰 Spin")
def spin_game(message):
    user_id = message.from_user.id
    spins = users.get(str(user_id), {}).get("spins", 0)
    if spins < 1:
        bot.send_message(user_id, "❌ Sizda spin yo‘q! Referral orqali ishlang.")
        return

    bot.send_animation(user_id, "https://media.giphy.com/media/3o6Zta2Xv3d0Xv4zC/giphy.gif", caption="🎰 Baraban aylanmoqda...")

    reward = random.randint(1000, 10000)
    users[str(user_id)]["balance"] += reward
    users[str(user_id)]["spins"] -= 1
    save_data("users.json", users)
    bot.send_message(user_id, f"✅ Siz {reward} so‘m yutdingiz!\n💰 Balansingiz: {users[str(user_id)]['balance']} so‘m")

# --- Bonus ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def daily(message):
    user_id = message.from_user.id
    today = date.today()
    if users.get(str(user_id), {}).get("last_bonus_date") == today:
        bot.send_message(user_id, "❌ Siz bonusni bugun oldingiz, ertaga yana urinib ko‘ring.")
        return

    users[str(user_id)]["balance"] += 5000
    users[str(user_id)]["last_bonus_date"] = today
    save_data("users.json", users)
    bot.send_message(user_id, f"🎁 Sizga 5000 so‘m bonus qo‘shildi!\n💰 Balans: {users[str(user_id)]['balance']}")

# --- Profil ---
@bot.message_handler(func=lambda m: m.text == "👤 Profil")
def profile(message):
    user_id = message.from_user.id
    balance = users.get(str(user_id), {}).get("balance", 0)
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
    except:
        bot.send_message(user_id, "❌ Raqam kiriting!")
        return

    if amount < 100000:
        bot.send_message(user_id, "❌ Minimal pul yechish 100000 so‘m.")
        return

    if users.get(str(user_id), {}).get("balance", 0) < amount:
        bot.send_message(user_id, "❌ Balansingizda mablag‘ yetarli emas.")
        return

    users[str(user_id)]["balance"] -= amount
    save_data("users.json", users)
    bot.send_message(user_id, f"✅ Pul yechish so‘rovi yuborildi.\n💸 Summasi: {amount} so‘m")
    bot.send_message(ADMIN_ID, f"💸 Yangi pul yechish so‘rovi!\n👤 ID: {user_id}\n💰 Summasi: {amount} so‘m")

# --- Referal ---
@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def referal(message):
    user_id = message.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    bot.send_message(user_id, f"👥 Do‘stlaringizni taklif qiling!\nReferal linkingiz:\n{link}")

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

@bot.message_handler(func=lambda m: m.text == "➖ Kanal o‘chirish" and m.from_user.id == ADMIN_ID)
def del_channel(message):
    if not channels:
        bot.send_message(ADMIN_ID, "❌ Hozircha kanal yo‘q.")
        return
    ch = channels.pop()
    save_channels(channels)
    bot.send_message(ADMIN_ID, f"❌ Kanal o‘chirildi: {ch}")

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.from_user.id == ADMIN_ID)
def stats(message):
    bot.send_message(ADMIN_ID, f"📊 Foydalanuvchilar soni: {len(user_balances)} ta\n📢 Kanallar: {', '.join(channels) if channels else 'yo‘q'}")

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
    app.run(host="0.0.0.0", port=port)

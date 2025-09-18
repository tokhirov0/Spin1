import os
import random
import json
import telebot
from flask import Flask, request
from dotenv import load_dotenv
import logging
from datetime import date

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

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Foydalanuvchilar va kanallar
try:
    with open("users.json", "r") as f:
        users = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    users = {}
    logger.info("users.json yaratildi yoki bo'sh bo'lib yuklandi.")

try:
    with open("channels.json", "r") as f:
        channels = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    channels = []
    logger.info("channels.json yaratildi yoki bo'sh bo'lib yuklandi.")

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f)
    logger.info("%s saqlandi.", file)

# /start handler
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    if channels:
        not_subscribed = []
        for ch in channels:
            try:
                status = bot.get_chat_member(ch, user_id).status
                if status in ["left", "kicked"]:
                    not_subscribed.append(ch)
            except:
                not_subscribed.append(ch)
        if not_subscribed:
            keyboard = telebot.types.InlineKeyboardMarkup()
            for ch in not_subscribed:
                keyboard.add(telebot.types.InlineKeyboardButton("Obuna bo‘lish", url=f"https://t.me/{ch[1:]}"))
            bot.send_message(user_id, "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling:", reply_markup=keyboard)
            return

    # Referral bonus
    if referrer_id and referrer_id != user_id and str(referrer_id) in users:
        users[str(referrer_id)]["spins"] += 1
        save_data("users.json", users)
        try:
            bot.send_message(referrer_id, "🎉 Do‘stingiz botga qo‘shildi! Sizga 1 ta spin qo‘shildi.")
        except:
            pass

    if str(user_id) not in users:
        users[str(user_id)] = {"balance":0, "spins":0, "referred_by": referrer_id, "last_bonus_date": None}
        save_data("users.json", users)

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🎰 Spin", "🎁 Bonus", "👤 Profil")
    keyboard.add("💸 Pul yechish", "👥 Referal")
    if str(user_id) == ADMIN_ID:
        keyboard.add("⚙️ Admin panel")
    bot.send_message(user_id, "Salom! Botga xush kelibsiz 👋", reply_markup=keyboard)

# Spin o‘yini
@bot.message_handler(func=lambda m: m.text=="🎰 Spin")
def spin_game(message):
    user_id = str(message.from_user.id)
    spins = users.get(user_id, {}).get("spins", 0)
    if spins < 1:
        bot.send_message(user_id, "❌ Sizda spin yo‘q!")
        return
    bot.send_animation(user_id, "https://media.giphy.com/media/3o6Zta2Xv3d0Xv4zC/giphy.gif", caption="🎰 Baraban aylanmoqda...")
    reward = random.randint(1000, 10000)
    users[user_id]["balance"] += reward
    users[user_id]["spins"] -= 1
    save_data("users.json", users)
    bot.send_message(user_id, f"✅ Siz {reward} so‘m yutdingiz!\n💰 Balansingiz: {users[user_id]['balance']} so‘m")

# Kunlik bonus
@bot.message_handler(func=lambda m: m.text=="🎁 Bonus")
def daily_bonus(message):
    user_id = str(message.from_user.id)
    today = str(date.today())
    if users[user_id].get("last_bonus_date") == today:
        bot.send_message(user_id, "❌ Bugun bonus olgansiz!")
        return
    users[user_id]["balance"] += 5000
    users[user_id]["last_bonus_date"] = today
    save_data("users.json", users)
    bot.send_message(user_id, f"🎁 Sizga 5000 so‘m bonus qo‘shildi!\n💰 Balansingiz: {users[user_id]['balance']} so‘m")

# Profil
@bot.message_handler(func=lambda m: m.text=="👤 Profil")
def profile(message):
    user_id = str(message.from_user.id)
    u = users.get(user_id, {})
    bot.send_message(user_id, f"👤 ID: <code>{user_id}</code>\n💰 Balans: {u.get('balance',0)} so‘m\n🎰 Spinlar: {u.get('spins',0)}\n👥 Taklif qiluvchi: {u.get('referred_by','Hech kim')}")

# Pul yechish
@bot.message_handler(func=lambda m: m.text=="💸 Pul yechish")
def withdraw(message):
    msg = bot.send_message(message.chat.id, "💸 Yechmoqchi bo‘lgan summani yozing:")
    bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
    user_id = str(message.from_user.id)
    try:
        amount = int(message.text)
    except:
        bot.send_message(user_id, "❌ Faqat raqam kiriting!")
        return
    if amount < 100000:
        bot.send_message(user_id, "❌ Minimal 100000 so‘m!")
        return
    if users[user_id]["balance"] < amount:
        bot.send_message(user_id, "❌ Balansingiz yetarli emas!")
        return
    users[user_id]["balance"] -= amount
    save_data("users.json", users)
    bot.send_message(user_id, f"✅ Pul yechish so‘rovi yuborildi: {amount} so‘m")
    bot.send_message(ADMIN_ID, f"💸 Yangi pul yechish!\nID: {user_id}\nSummasi: {amount} so‘m")

# Referral
@bot.message_handler(func=lambda m: m.text=="👥 Referal")
def referal(message):
    user_id = str(message.from_user.id)
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    bot.send_message(user_id, f"👥 Do‘stlaringizni taklif qiling!\nHar bir do‘st uchun 1 spin!\n{referral_link}")

# Admin panel
@bot.message_handler(func=lambda m: m.text=="⚙️ Admin panel" and str(message.from_user.id)==ADMIN_ID)
def admin_panel(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("➕ Kanal qo‘shish", "➖ Kanal o‘chirish")
    keyboard.add("📊 Statistika", "⬅️ Orqaga")
    bot.send_message(ADMIN_ID, "⚙️ Admin panel", reply_markup=keyboard)

# Flask webhook
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Bot faqat Telegram orqali ishlaydi!", 200

def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook o‘rnatildi: {WEBHOOK_URL}")

if __name__=="__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)

import os
import json
import telebot
from flask import Flask, request
from dotenv import load_dotenv
import requests
import logging

# Logging sozlamalari (xatolarni kuzatish uchun)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment o'zgaruvchilarini yuklash
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN topilmadi!")
    exit(1)
RENDER_URL = os.getenv("RENDER_URL")
if not RENDER_URL:
    logger.error("RENDER_URL topilmadi!")
    exit(1)
ADMIN_ID = os.getenv("ADMIN_ID")
if not ADMIN_ID:
    logger.error("ADMIN_ID topilmadi!")
    exit(1)
PORT = int(os.getenv("PORT", 10000))

# Bot va Flask serverni boshlash
bot = telebot.TeleBot(BOT_TOKEN)
server = Flask(__name__)

# Kanallar faylini yuklash
try:
    with open("channels.json", "r") as f:
        channels = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    channels = []
    logger.info("channels.json yaratildi yoki bo'sh bo'lib yuklandi.")

# Kanallarni saqlash funksiyasi
def save_channels():
    with open("channels.json", "w") as f:
        json.dump(channels, f)
    logger.info("Kanallar saqlandi: %s", channels)

# /start buyrug'i uchun handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    logger.info("Foydalanuvchi ID: %s /start ni boshladi", user_id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(telebot.types.KeyboardButton("🎰 Spin"), telebot.types.KeyboardButton("🎁 Bonus"))
    markup.row(telebot.types.KeyboardButton("👤 Profil"))
    if str(user_id) == ADMIN_ID:  # Adminni tekshirish
        markup.row(telebot.types.KeyboardButton("⚙️ Admin panel"))
    bot.send_message(message.chat.id, "Assalomu alaykum! Botga xush kelibsiz!", reply_markup=markup)

# Profil ma'lumotlari
@bot.message_handler(lambda message: message.text == "👤 Profil")
def show_profile(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Noma'lum"
    logger.info("Foydalanuvchi %s profilda", user_id)
    bot.send_message(message.chat.id, f"📋 Sizning ID: {user_id}\n📅 Ro'yxatdan o'tgan vaqt: @{username}")

# Webhook handler
@server.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    logger.info("Webhook so'rovi qabul qilindi")
    return "OK", 200

# Admin panel inline keyboard
def get_admin_markup():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("➕ Kanal qo‘shish", callback_data="add_channel"))
    markup.row(telebot.types.InlineKeyboardButton("➖ Kanal o‘chirish", callback_data="remove_channel"))
    markup.row(telebot.types.InlineKeyboardButton("📊 Statistika", callback_data="stats"))
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back"))
    return markup

# Admin panelga kirish
@bot.message_handler(lambda message: message.text == "⚙️ Admin panel" and str(message.from_user.id) == ADMIN_ID)
def admin_panel(message):
    logger.info("Admin %s panelga kirdi", message.from_user.id)
    markup = get_admin_markup()
    bot.send_message(message.chat.id, "⚙️ Admin panelga xush kelibsiz!", reply_markup=markup)

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    logger.info("Callback: %s, User ID: %s", call.data, user_id)
    if str(user_id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Siz admin emassiz!")
        return

    if call.data == "add_channel":
        msg = bot.send_message(call.message.chat.id, "📝 @ bilan kanal username'ni kiriting (masalan: @mychannel)")
        bot.register_next_step_handler(msg, process_channel_add)

    elif call.data == "remove_channel":
        if not channels:
            bot.answer_callback_query(call.id, "❌ Hozircha kanal yo‘q")
        else:
            removed_channel = channels.pop()
            save_channels()
            bot.answer_callback_query(call.id, f"❌ Kanal o‘chirildi: {removed_channel}")

    elif call.data == "stats":
        try:
            user_count = len(set([msg.from_user.id for msg in bot.get_updates() if msg.message]))
            bot.answer_callback_query(call.id, f"📊 Foydalanuvchilar soni: {user_count} ta\n📢 Kanallar: {', '.join(channels) or 'Yo‘q'}")
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ Statistika yuklanmadi!")
            logger.error("Statistika xatosi: %s", e)

    elif call.data == "back":
        bot.edit_message_text("⚙️ Admin paneldan chiqdingiz!", call.message.chat.id, call.message.message_id)
        send_welcome(telebot.types.Message.de_json({"chat": {"id": call.message.chat.id}, "from_user": call.from_user}))

# Kanal qo‘shish funksiyasi
def process_channel_add(message):
    channel = message.text
    logger.info("Kanal qo‘shish urunish: %s", channel)
    if channel.startswith("@") and len(channel) > 1:
        try:
            response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id={channel}")
            data = response.json()
            if data["ok"]:
                if channel not in channels:
                    channels.append(channel)
                    save_channels()
                    bot.reply_to(message, f"✅ Kanal qo‘shildi: {channel}")
                else:
                    bot.reply_to(message, f"❗ {channel} allaqachon qo‘shilgan!")
            else:
                bot.reply_to(message, "❌ Kanal topilmadi yoki botda ruxsat yo‘q!")
        except Exception as e:
            bot.reply_to(message, "❌ Xatolik yuz berdi, qayta urining!")
            logger.error("Kanal qo‘shish xatosi: %s", e)
    else:
        bot.reply_to(message, "❌ Noto‘g‘ri format! @ bilan boshlang (masalan: @mychannel)")

# Webhookni o‘rnatish
def set_webhook():
    url = RENDER_URL + BOT_TOKEN
    try:
        bot.set_webhook(url=url)
        logger.info("Webhook o‘rnatildi: %s", url)
    except Exception as e:
        logger.error("Webhook o‘rnatish xatosi: %s", e)

# Serverni ishga tushirish
if __name__ == "__main__":
    set_webhook()
    server.run(host="0.0.0.0", port=PORT)

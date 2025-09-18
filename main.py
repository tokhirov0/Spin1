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

# Bot va Flask serverni boshlash
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Foydalanuvchi va kanal ma'lumotlarini yuklash
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

# /start buyrug'i (referral bilan)
@bot.message_handler(commands=['start'])  # To'g'ri list sifatida
def send_welcome(message):
    user_id = message.from_user.id
    referred_by = None
    if len(message.text.split()) > 1:  # Referral kodini tekshirish
        referred_by = message.text.split()[1]
        if referred_by.isdigit() and int(referred_by) != user_id and referred_by in users:
            users[referred_by]["spins"] = users.get(referred_by, {}).get("spins", 0) + 1
            save_data("users.json", users)
            try:
                bot.send_message(int(referred_by), "🎉 Do‘stingiz botga qo‘shildi! Sizga 1 ta spin qo‘shildi.")
            except Exception as e:
                logger.error("Referal xabari yuborishda xatolik: %s", e)

    if str(user_id) not in users:
        users[str(user_id)] = {"balance": 0, "spins": 0, "referred_by": referred_by}
        save_data("users.json", users)

    logger.info("Foydalanuvchi ID: %s /start ni boshladi, referred_by: %s", user_id, referred_by)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎰 Spin", "🎁 Bonus")
    markup.row("👤 Profil", "👥 Referal")
    markup.row("💸 Pul yechish")
    if str(user_id) == ADMIN_ID:
        markup.row("⚙️ Admin panel")
    bot.send_message(message.chat.id, "Assalomu alaykum! Botga xush kelibsiz! 👋", reply_markup=markup)

# Profil ma'lumotlari
@bot.message_handler(func=lambda message: message.text == "👤 Profil")
def show_profile(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Noma'lum"
    balance = users.get(str(user_id), {}).get("balance", 0)
    spins = users.get(str(user_id), {}).get("spins", 0)
    referred_by = users.get(str(user_id), {}).get("referred_by", "Hech kim")
    logger.info("Foydalanuvchi %s profilda", user_id)
    bot.send_message(message.chat.id, f"👤 ID: <code>{user_id}</code>\n📅 Username: @{username}\n💰 Balans: {balance} so‘m\n🎰 Spinlar: {spins}\n👥 Taklif qiluvchi: {referred_by}")

# Spin o'yini (GIF bilan)
@bot.message_handler(func=lambda message: message.text == "🎰 Spin")
def spin_game(message):
    user_id = message.from_user.id
    spins = users.get(str(user_id), {}).get("spins", 0)
    if spins < 1:
        bot.send_message(message.chat.id, "❌ Sizda spin yo‘q! Referral orqali ishlang.")
        return

    # GIF yuborish
    gif_url = "https://media.giphy.com/media/3o6Zta2Xv3d0Xv4zC/giphy.gif"  # Slot machine GIF
    bot.send_animation(message.chat.id, gif_url, caption="🎰 Baraban aylanmoqda...")

    reward = random.randint(1000, 10000)  # 1000-10000 so‘m
    users[str(user_id)]["balance"] += reward
    users[str(user_id)]["spins"] -= 1
    save_data("users.json", users)
    bot.send_message(message.chat.id, f"✅ Siz {reward} so‘m yutdingiz!\n💰 Balansingiz: {users[str(user_id)]['balance']} so‘m\n🎰 Qolgan spinlar: {users[str(user_id)]['spins']}")

# Bonus (placeholder)
@bot.message_handler(func=lambda message: message.text == "🎁 Bonus")
def bonus_message(message):
    bot.send_message(message.chat.id, "🎁 Bonus hali mavjud emas, tez orada qo‘shiladi!")

# Pul yechish
@bot.message_handler(func=lambda message: message.text == "💸 Pul yechish")
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

    balance = users.get(str(user_id), {}).get("balance", 0)
    if balance < amount:
        bot.send_message(user_id, "❌ Balansingizda mablag‘ yetarli emas.")
        return

    users[str(user_id)]["balance"] -= amount
    save_data("users.json", users)
    bot.send_message(user_id, f"✅ Pul yechish so‘rovi yuborildi.\n💸 Summasi: {amount} so‘m")
    if str(user_id) != ADMIN_ID:
        bot.send_message(ADMIN_ID, f"💸 Yangi pul yechish so‘rovi!\n👤 ID: {user_id}\n💰 Summasi: {amount} so‘m")

# Referal bo‘limi
@bot.message_handler(func=lambda message: message.text == "👥 Referal")
def referal(message):
    user_id = message.from_user.id
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Referal yuborish")
    bot.send_message(message.chat.id, f"👥 Do‘stlaringizni taklif qiling!\nHar bir do‘stingiz uchun bitta imkoniyat olasiz!\nReferal linkingiz: {referral_link}", reply_markup=markup)

# Referal yuborish
@bot.message_handler(func=lambda message: message.text == "Referal yuborish")
def send_referal(message):
    user_id = message.from_user.id
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    bot.send_message(message.chat.id, f"Yangi foydalanuvchilarga yuboring:\n{referral_link}")

# Admin panel inline keyboard
def get_admin_markup():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("➕ Kanal qo‘shish", callback_data="add_channel"))
    markup.row(telebot.types.InlineKeyboardButton("➖ Kanal o‘chirish", callback_data="remove_channel"))
    markup.row(telebot.types.InlineKeyboardButton("📊 Statistika", callback_data="stats"))
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Orqaga", callback_data="back"))
    return markup

# Admin panelga kirish
@bot.message_handler(func=lambda message: message.text == "⚙️ Admin panel" and str(message.from_user.id) == ADMIN_ID)
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
            save_data("channels.json", channels)
            bot.answer_callback_query(call.id, f"❌ Kanal o‘chirildi: {removed_channel}")

    elif call.data == "stats":
        user_count = len(users)
        bot.answer_callback_query(call.id, f"📊 Foydalanuvchilar soni: {user_count} ta\n📢 Kanallar: {', '.join(channels) or 'Yo‘q'}")

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
                    save_data("channels.json", channels)
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

# Webhook handler
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    logger.info("Webhook so'rovi qabul qilindi")
    return "OK", 200

# Webhookni o‘rnatish
def set_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook o‘rnatildi: %s", WEBHOOK_URL)
    except Exception as e:
        logger.error("Webhook o‘rnatish xatosi: %s", e)

# Serverni ishga tushirish
if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=PORT)

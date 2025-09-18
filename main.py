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

# Bot va Flask ilovasini ishga tushirish
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Foydalanuvchilar va kanallar fayllarini yuklash
try:
  with open("users.json", "r") as f:
      users = json.load(f)  # {user_id: {"balance": 0, "spins": 0, "referred_by": None, "last_bonus_date": None}}
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

  # Kanal tekshiruvi
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
  if referrer_id and referrer_id != user_id and str(referrer_id) in users:
      referrer_spins = users.get(str(referrer_id), {}).get("spins", 0)
      users[str(referrer_id)] = {"balance": users.get(str(referrer_id), {}).get("balance", 0), 
                               "spins": referrer_spins + 1, 
                               "referred_by": None, 
                               "last_bonus_date": users.get(str(referrer_id), {}).get("last_bonus_date")}
      save_data("users.json", users)
      try:
          bot.send_message(referrer_id, "🎉 Do‘stingiz botga qo‘shildi! Sizga 1 ta spin qo‘shildi.")
      except Exception as e:
          logger.error(f"Referal xabari yuborishda xatolik: {e}")

  # Yangi foydalanuvchi qo‘shish
  if str(user_id) not in users:
      users[str(user_id)] = {"balance": 0, "spins": 0, "referred_by": referrer_id, "last_bonus_date": None}
      save_data("users.json", users)

  # Keyboard
  keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
  keyboard.add("🎰 Spin", "🎁 Bonus", "👤 Profil")
  keyboard.add("💸 Pul yechish", "👥 Referal")
  if user_id == int(ADMIN_ID):
      keyboard.add("⚙️ Admin panel")
  bot.send_message(user_id, "Salom! Botga xush kelibsiz 👋", reply_markup=keyboard)

# Spin o'yini
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

# Kunlik bonus
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def daily_bonus(message):
  user_id = message.from_user.id
  today = date.today()
  last_bonus = users.get(str(user_id), {}).get("last_bonus_date")
  if last_bonus == today:
      bot.send_message(user_id, "❌ Siz bugun bonusni oldingiz, ertaga qayta urinib ko‘ring!")
      return

  users[str(user_id)]["balance"] += 5000
  users[str(user_id)]["last_bonus_date"] = today
  save_data("users.json", users)
  bot.send_message(user_id, f"🎁 Sizga 5000 so‘m bonus qo‘shildi!\n💰 Balansingiz: {users[str(user_id)]['balance']} so‘m")

# Profil ko‘rsatish
@bot.message_handler(func=lambda m: m.text == "👤 Profil")
def profile(message):
  user_id = message.from_user.id
  balance = users.get(str(user_id), {}).get("balance", 0)
  spins = users.get(str(user_id), {}).get("spins", 0)
  referred_by = users.get(str(user_id), {}).get("referred_by", "Hech kim")
  bot.send_message(user_id, f"👤 ID: <code>{user_id}</code>\n💰 Balans: {balance} so‘m\n🎰 Spinlar: {spins}\n👥 Taklif qiluvchi: {referred_by}")

# Pul yechish
@bot.message_handler(func=lambda m: m.text == "💸 Pul yechish")
def withdraw(message):
  msg = bot.send_message(message.chat.id, "💸 Yechmoqchi bo‘lgan summani yozing (minimal 100000 so‘m):")
  bot.register_next_step_handler(msg, process_withdraw)

def process_withdraw(message):
  user_id = message.from_user.id
  try:
      amount = int(message.text)
  except ValueError:
      bot.send_message(user_id, "❌ Faqat raqam kiriting!")
      return

  if amount < 100000:
      bot.send_message(user_id, "❌ Minimal pul yechish 100000 so‘m!")
      return

  balance = users.get(str(user_id), {}).get("balance", 0)
  if balance < amount:
      bot.send_message(user_id, "❌ Balansingizda yetarli mablag‘ yo‘q!")
      return

  users[str(user_id)]["balance"] -= amount
  save_data("users.json", users)
  bot.send_message(user_id, f"✅ Pul yechish so‘rovi yuborildi: {amount} so‘m")
  if user_id != int(ADMIN_ID):
      bot.send_message(ADMIN_ID, f"💸 Yangi pul yechish so‘rovi!\n👤 ID: {user_id}\n💰 Summasi: {amount} so‘m")

# Referral tizimi
@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def referal(message):
  user_id = message.from_user.id
  referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
  bot.send_message(user_id, f"👥 Do‘stlaringizni taklif qiling!\nHar bir do‘st uchun 1 spin olasiz!\nReferal linkingiz:\n{referral_link}")

# Admin paneli
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin panel" and m.from_user.id == int(ADMIN_ID))
def admin_panel(message):
  keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
  keyboard.add("➕ Kanal qo‘shish", "➖ Kanal o‘chirish")
  keyboard.add("📊 Statistika", "⬅️ Orqaga")
  bot.send_message(ADMIN_ID, "⚙️ Admin panelga xush kelibsiz!", reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "➕ Kanal qo‘shish" and m.from_user.id == int(ADMIN_ID))
def add_channel(message):
  msg = bot.send_message(ADMIN_ID, "➕ Kanal username’ni kiriting (@ bilan, masalan: @mychannel):")
  bot.register_next_step_handler(msg, save_channel)

def save_channel(message):
  channel = message.text.strip()
  if not channel.startswith("@") or len(channel) < 2:
      bot.send_message(ADMIN_ID, "❌ Noto‘g‘ri format! @ bilan boshlang (masalan: @mychannel).")
      return
  try:
      bot.get_chat_member(channel, ADMIN_ID)  # Ruxsat tekshiruvi
      if channel not in channels:
          channels.append(channel)
          save_data("channels.json", channels)
          bot.send_message(ADMIN_ID, f"✅ Kanal qo‘shildi: {channel}")
      else:
          bot.send_message(ADMIN_ID, f"❗ {channel} allaqachon qo‘shilgan!")
  except Exception as e:
      bot.send_message(ADMIN_ID, f"❌ Kanal topilmadi yoki botda ruxsat yo‘q: {e}")
      logger.error(f"Kanal qo‘shishda xatolik: {e}")

@bot.message_handler(func=lambda m: m.text == "➖ Kanal o‘chirish" and m.from_user.id == int(ADMIN_ID))
def del_channel(message):
  if not channels:
      bot.send_message(ADMIN_ID, "❌ Hozircha kanal ro‘yxatda yo‘q.")
      return
  removed_channel = channels.pop()
  save_data("channels.json", channels)
  bot.send_message(ADMIN_ID, f"❌ Kanal o‘chirildi: {removed_channel}")

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and m.from_user.id == int(ADMIN_ID))
def stats(message):
  user_count = len(users)
  bot.send_message(ADMIN_ID, f"📊 Foydalanuvchilar soni: {user_count} ta\n📢 Kanallar: {', '.join(channels) if channels else 'Yo‘q'}")

@bot.message_handler(func=lambda m: m.text == "⬅️ Orqaga" and m.from_user.id == int(ADMIN_ID))
def back(message):
  start(message)

# Flask webhook handler
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
  try:
      json_string = request.get_data().decode("utf-8")
      update = telebot.types.Update.de_json(json_string)
      bot.process_new_updates([update])
      logger.info(f"Webhook so'rovi qabul qilindi: {json_string[:100]}")
      return "OK", 200
  except Exception as e:
      logger.error(f"Webhook xatosi: {e}")
      return "Error", 500

# Asosiy sahifa handler
@app.route("/")
def index():
  return "Bot faqat Telegram orqali ishlaydi!", 200

# Webhookni o‘rnatish
def set_webhook():
  try:
      bot.remove_webhook()
      bot.set_webhook(url=WEBHOOK_URL)
      logger.info(f"Webhook o‘rnatildi: {WEBHOOK_URL}")
  except Exception as e:
      logger.error(f"Webhook o‘rnatishda xato: {e}")

# Serverni ishga tushirish
if __name__ == "__main__":
  set_webhook()
  app.run(host="0.0.0.0", port=PORT)

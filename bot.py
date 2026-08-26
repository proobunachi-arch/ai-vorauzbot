import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Message,
)

# --- ASOSIY SOZLAMALAR ---
BOT_TOKEN = "8915804782:AAFbDTx-SGjjTz1DGrBjCCYWq15jSJBCLe4"
ADMIN_ID =7828382485 # O'z Telegram ID raqamingizni yozing

# Majburiy obuna tekshiriladigan kanal
CHANNEL_ID = "@AIVORA_UZ"

# Sizning Telegram username'ingiz
ADMIN_USERNAME = "ABDRFV_11"

logging.basicConfig(level=logging.INFO)
router = Router()


# --- BAZA BILAN ISHLASH ---
def db_start():
  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            referrer_id INTEGER,
            balance INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            product_type TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

  default_settings = {
      "card_number": "8600 1234 5678 9012",
      "card_holder": "ABDRFV M.",  # Karta egasining ismi
      "gemini_price": "50000",
      "course_price": "100000",
      "channel_link": "https://t.me/AIVORA_UZ",
  }

  for key, value in default_settings.items():
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )

  conn.commit()
  conn.close()


db_start()


def get_setting(key):
  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
  res = cursor.fetchone()
  conn.close()
  return res[0] if res else ""


def update_setting(key, value):
  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute(
      "UPDATE settings SET value = ? WHERE key = ?", (value, key)
  )
  conn.commit()
  conn.close()


# --- MAJBURIY OBUNANI TEKshirish ---
async def check_subscription(user_id: int, bot: Bot) -> bool:
  try:
    member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
    if member.status in ["left", "kicked"]:
      return False
    return True
  except Exception as e:
    logging.error(f"Obunani tekshirishda xatolik: {e}")
    return False


# FSM holatlari
class PaymentState(StatesGroup):
  waiting_for_receipt = State()
  product_type = State()


class AdminState(StatesGroup):
  waiting_for_new_value = State()
  setting_key = State()


class BroadcastState(StatesGroup):
  waiting_for_message = State()


# --- PASTDAGI ASOSIY TUGMALAR (ReplyKeyboardMarkup) ---
def main_reply_keyboard(user_id):
  keyboard = [
      [KeyboardButton(text="🛍️ Do'kon"), KeyboardButton(text="👤 Profil")],
      [
          KeyboardButton(text="🤖 Gemini Pro nima?"),
          KeyboardButton(text="📖 Yo'riqnoma"),
      ],
      [KeyboardButton(text="📞 Yordam")],
  ]
  if user_id == ADMIN_ID:
    keyboard.append([KeyboardButton(text="🛠️ Admin Panel")])
  return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# Ichki pullik xizmatlar menyusi (Inline)
def paid_menu():
  gemini_p = get_setting("gemini_price")
  course_p = get_setting("course_price")
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text=f"🤖 Gemini Pro obunasi — {int(gemini_p):,} so'm".replace(
                      ",", " "
                  ),
                  callback_data="buy_gemini",
              )
          ],
          [
              InlineKeyboardButton(
                  text=(
                      "🎥 Yopiq kanal va AI video darslar —"
                      f" {int(course_p):,} so'm".replace(",", " ")
                  ),
                  callback_data="buy_course",
              )
          ],
      ]
  )


# --- /START VA OBUNANI TEKSHIRISH ---
@router.message(CommandStart())
async def cmd_start(message: Message):
  user_id = message.from_user.id

  is_subscribed = await check_subscription(user_id, message.bot)
  channel_link_db = get_setting("channel_link")

  if not is_subscribed:
    await message.answer(
        f"❌ <b>Botdan foydalanish uchun avval {CHANNEL_ID} kanalimizga obuna bo'lishingiz kerak!</b>\n\nKanalga a'zo bo'lgach, <b>🔄 Tekshirish</b> tugmasini bosing.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📢 Kanalga obuna bo'lish", url=channel_link_db
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Tekshirish", callback_data="check_sub"
                    )
                ],
            ]
        ),
        parse_mode="HTML",
    )
    return

  full_name = message.from_user.full_name
  username = message.from_user.username

  args = message.text.split()
  referrer_id = None
  if len(args) > 1 and args[1].isdigit():
    ref_id = int(args[1])
    if ref_id != user_id:
      referrer_id = ref_id

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
  user = cursor.fetchone()

  if not user:
    cursor.execute(
        "INSERT INTO users (user_id, full_name, username, referrer_id) VALUES"
        " (?, ?, ?, ?)",
        (user_id, full_name, username, referrer_id),
    )
    if referrer_id:
      cursor.execute(
          "UPDATE users SET referrals_count = referrals_count + 1 WHERE"
          " user_id = ?",
          (referrer_id,),
      )
      cursor.execute(
          "SELECT referrals_count FROM users WHERE user_id = ?", (referrer_id,)
      )
      ref_count = cursor.fetchone()[0]

      if ref_count >= 10:
        try:
          await message.bot.send_message(
              referrer_id,
              "🎉 Tabriklaymiz! 10 ta do'st taklif qildingiz va shartni"
              f" bajardingiz!\n\nIltimos, @{ADMIN_USERNAME} ga yozing, u sizga"
              " obunani olib beradi.",
              reply_markup=InlineKeyboardMarkup(
                  inline_keyboard=[
                      [
                          InlineKeyboardButton(
                              text=f"👤 @{ADMIN_USERNAME} ga yozish",
                              url=f"https://t.me/{ADMIN_USERNAME}",
                          )
                      ]
                  ]
              ),
          )
        except:
          pass
    conn.commit()
  conn.close()

  await message.answer(
      f"Assalomu alaykum, <b>{full_name}</b>!\n\n🤖 Xush kelibsiz! Kerakli"
      " bo'limni pastdagi tugmalar orqali tanlang.",
      reply_markup=main_reply_keyboard(user_id),
      parse_mode="HTML",
  )


@router.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
  user_id = callback.from_user.id
  is_subscribed = await check_subscription(user_id, callback.bot)

  if not is_subscribed:
    await callback.answer(
        "❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True
    )
    return

  await callback.message.delete()
  fake_message = callback.message
  fake_message.text = "/start"
  await cmd_start(fake_message)


# --- /YORDAM VA /HELP BUYRUQLARI ---
@router.message(Command("help"))
@router.message(Command("yordam"))
@router.message(F.text == "📞 Yordam")
async def help_handler(message: Message):
  user_id = message.from_user.id
  if not await check_subscription(user_id, message.bot):
    await message.answer("❌ Avval kanalga obuna bo'ling!")
    return

  help_text = (
      "🛠 <b>Yordam markazi</b>\n\nSavollar yoki muammolar bo'yicha"
      f" to'g'ridan-to'g'ri adminga murojaat qilishingiz mumkin:\n\n👤 Admin:"
      f" <b>@{ADMIN_USERNAME}</b>"
  )
  await message.answer(
      help_text,
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text=f"💬 @{ADMIN_USERNAME} ga yozish",
                      url=f"https://t.me/{ADMIN_USERNAME}",
                  )
              ]
          ]
      ),
      parse_mode="HTML",
  )


# --- DO'KON BO'LIMI ---
@router.message(F.text == "🛍️ Do'kon")
async def shop_handler(message: Message):
  user_id = message.from_user.id
  if not await check_subscription(user_id, message.bot):
    await message.answer("❌ Avval kanalga obuna bo'ling!")
    return

  await message.answer(
      "🛒 <b>Mavjud xizmatlar va mahsulotlar:</b>\n\nQuyidagilardan birini"
      " tanlang:",
      reply_markup=paid_menu(),
      parse_mode="HTML",
  )


# --- PROFIL VA REFERRAL ---
@router.message(F.text == "👤 Profil")
async def profile_handler(message: Message):
  user_id = message.from_user.id
  if not await check_subscription(user_id, message.bot):
    await message.answer("❌ Avval kanalga obuna bo'ling!")
    return

  bot_info = await message.bot.get_me()
  ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT referrals_count FROM users WHERE user_id = ?", (user_id,)
  )
  count = cursor.fetchone()[0]
  conn.close()

  text = (
      f"👤 <b>Sizning profilingiz:</b>\n\nID: <code>{user_id}</code>\n👥 Taklif"
      f" qilgan do'stlaringiz: <b>{count} / 10</b>\n\n🔗 <b>Shaxsiy referral"
      f" havolangiz:</b>\n{ref_link}\n\n💡 10 ta do'st taklif qiling va @"
      f"{ADMIN_USERNAME} orqali Gemini Pro obunasini tekin qo'lga kiriting!"
  )
  await message.answer(text, parse_mode="HTML")


# --- GEMINI PRO HAQIDA MA'LUMOT ---
@router.message(F.text == "🤖 Gemini Pro nima?")
async def gemini_info_message(message: Message):
  user_id = message.from_user.id
  if not await check_subscription(user_id, message.bot):
    await message.answer("❌ Avval kanalga obuna bo'ling!")
    return

  info_text = (
      "<b>Obunaga nimalar kiradi?</b> 🤔\n\n"
      "✅ <b>Gemini Pro</b> — matn yozish, tarjima qilish, dasturlash, tahlil"
      " va kundalik ishlar uchun kuchli AI yordamchi. 🧠✨\n\n⭐ <b>Antigravity</b>"
      " — kod yozish, kodni tahlil qilish va murakkab dasturlash vazifalari"
      " uchun. 💻⚙️\n\n✅ <b>Flow</b> — AI yordamida video yaratish. 🎬 Har"
      " oy 1000 ta kredit beriladi. 🎁\n\n🟠 <b>Nano Banana</b> — rasmlar"
      " yaratish va ularni AI yordamida tahrirlash. 🎨🖌️\n\n✅️ <b>Veo 3</b> —"
      " yuqori sifatli va realistlik AI videolar yaratish. 📷🚀\n\n✅"
      " <b>NotebookLM</b> — PDF, Word va boshqa hujjatlar bilan ishlash,"
      " konspekt tuzish va savollarga javob olish. 📚🗒\n\n✅ <b>5 TB xotira"
      " ⬇️</b>\n\n-----------------------------\n<b>Kimlar"
      " uchun?</b> 👇\n\n👨‍🎓 Talabalar\n🖥 Dasturchilar\n🖌"
      " Dizaynerlar\n📈 Marketologlar va SMM mutaxassislari\n🎥 Kontent"
      " yaratuvchilar\n📱 Amerika YouTube'da AI Videolar Qilib Pul"
      " Ishlaydiganlar uchun ✅\n🚀 AI imkoniyatlaridan maksimal foydalanishni"
      " istagan har bir kishi.\n\n<b>Narxi 18 oy uchun✅</b>"
  )
  await message.answer(
      info_text,
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text=f"👤 @{ADMIN_USERNAME} ga yozish",
                      url=f"https://t.me/{ADMIN_USERNAME}",
                  )
              ]
          ]
      ),
      parse_mode="HTML",
  )


# --- YO'RIQNOMA ---
@router.message(F.text == "📖 Yo'riqnoma")
async def guide_handler(message: Message):
  user_id = message.from_user.id
  if not await check_subscription(user_id, message.bot):
    await message.answer("❌ Avval kanalga obuna bo'ling!")
    return

  await message.answer(
      "📖 <b>Botdan foydalanish yo'riqnomasi:</b>\n\n1. 🛍️ <b>Do'kon</b>"
      " bo'limidan o'zingizga kerakli xizmatni tanlang.\n2. Taqdim etilgan"
      " karta raqamiga to'lovni amalga oshiring.\n3. To'lov cheki (skrinshot)"
      " rasmini botga yuboring.\n4. Admin tasdiqlagach, @"
      f"<b>{ADMIN_USERNAME}</b> siz bilan bog'lanadi yoki kanal havolasini"
      " beradi.\n\nShuningdek, 10 ta do'st taklif qilib ham tekin obuna"
      " olishingiz mumkin!",
      parse_mode="HTML",
  )


# --- TO'LOV JARAYONI ---
@router.callback_query(F.data.in_({"buy_gemini", "buy_course"}))
async def start_payment(callback: CallbackQuery, state: FSMContext):
  is_gemini = callback.data == "buy_gemini"
  price = get_setting("gemini_price") if is_gemini else get_setting("course_price")
  product = (
      f"Gemini Pro Obunasi ({int(price):,} so'm)".replace(",", " ")
      if is_gemini
      else f"Yopiq kanal va AI kurs ({int(price):,} so'm)".replace(",", " ")
  )

  await state.set_state(PaymentState.waiting_for_receipt)
  await state.update_data(product_type=product, price=int(price))

  card_number = get_setting("card_number")
  card_holder = get_setting("card_holder")

  text = (
      f"💳 <b>To'lov qilish uchun:</b>\n\nMahsulot:"
      f" <b>{product}</b>\nSumma: <b>{int(price):,} so'm</b>\n\nKarta raqami:"
      f" <code>{card_number}</code>\nKarta egasi: <b>{card_holder}</b>\n\nPulni"
      " o'tkazgandan so'ng, to'lov cheki (skrinshot) rasmini shu yerga"
      " yuboring."
  )
  await callback.message.answer(
      text.replace(",", " "), parse_mode="HTML"
  )
  await callback.answer()


@router.message(PaymentState.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext):
  data = await state.get_data()
  product_type = data.get("product_type")
  price = data.get("price")
  photo_id = message.photo[-1].file_id
  user = message.from_user

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO payments (user_id, amount, product_type) VALUES (?, ?, ?)",
      (user.id, price, product_type),
  )
  payment_id = cursor.lastrowid
  conn.commit()
  conn.close()

  await state.clear()
  await message.answer(
      "✅ Chekingiz adminga yuborildi! Tekshirilib, tez orada javob"
      " beriladi.",
      reply_markup=main_reply_keyboard(user.id),
  )

  admin_text = (
      f"📥 <b>Yangi to'lov cheki!</b>\n\nFoydalanuvchi: {user.full_name} "
      f"(@{user.username}, ID: <code>{user.id}</code>)\nMahsulot:"
      f" <b>{product_type}</b>"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Tasdiqlash", callback_data=f"approve_{payment_id}_{user.id}"
              ),
              InlineKeyboardButton(
                  text="❌ Rad etish", callback_data=f"reject_{payment_id}_{user.id}"
              ),
          ]
      ]
  )
  await message.bot.send_photo(
      ADMIN_ID, photo=photo_id, caption=admin_text, reply_markup=keyboard, parse_mode="HTML"
  )


# --- ADMIN PANEL VA SOZLAMALAR ---
@router.message(F.text == "🛠️ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel_message(message: Message):
  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT COUNT(*) FROM users")
  users_count = cursor.fetchone()[0]
  cursor.execute("SELECT COUNT(*) FROM payments")
  payments_count = cursor.fetchone()[0]
  conn.close()

  card = get_setting("card_number")
  holder = get_setting("card_holder")
  g_price = get_setting("gemini_price")
  c_price = get_setting("course_price")

  text = (
      f"🛠️ <b>Admin Panel</b>\n\nJami foydalanuvchilar: <b>{users_count}</b>"
      f" ta\nJami to'lovlar: <b>{payments_count}</b>"
      f" ta\n\n-------------------\n💳 Karta: <code>{card}</code>\n👤 Karta"
      f" egasi: <b>{holder}</b>\n🤖 Gemini Narxi: <b>{g_price} so'm</b>\n🎥 Kurs"
      f" Narxi: <b>{c_price} so'm</b>"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💳 Karta raqamni o'zgartirish", callback_data="edit_card"
              )
          ],
          [
              InlineKeyboardButton(
                  text="👤 Karta egasini o'zgartirish",
                  callback_data="edit_holder",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🤖 Gemini narxini o'zgartirish",
                  callback_data="edit_gemini_price",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🎥 Kurs narxini o'zgartirish",
                  callback_data="edit_course_price",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📢 Kanal havolasini o'zgartirish",
                  callback_data="edit_channel_link",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📢 Botga xabar/reklama tarqatish",
                  callback_data="broadcast",
              )
          ],
      ]
  )
  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(
    F.data.in_(
        {
            "edit_card",
            "edit_holder",
            "edit_gemini_price",
            "edit_course_price",
            "edit_channel_link",
        }
    ),
    F.from_user.id == ADMIN_ID,
)
async def edit_setting_start(callback: CallbackQuery, state: FSMContext):
  key_map = {
      "edit_card": ("card_number", "Yangi karta raqamini kiriting:"),
      "edit_holder": ("card_holder", "Yangi karta egasining ismini kiriting:"),
      "edit_gemini_price": ("gemini_price", "Gemini Pro uchun yangi narx:"),
      "edit_course_price": ("course_price", "Kurs uchun yangi narx:"),
      "edit_channel_link": (
          "channel_link",
          "Kanal uchun yangi havolani kiriting:",
      ),
  }

  setting_key, prompt_text = key_map[callback.data]
  await state.set_state(AdminState.waiting_for_new_value)
  await state.update_data(setting_key=setting_key)

  await callback.message.edit_text(f"✍️ {prompt_text}")


@router.message(AdminState.waiting_for_new_value, F.from_user.id == ADMIN_ID)
async def save_new_setting(message: Message, state: FSMContext):
  data = await state.get_data()
  setting_key = data.get("setting_key")
  new_value = message.text.strip()

  update_setting(setting_key, new_value)
  await state.clear()

  await message.answer(
      "✅ Muvaffaqiyatli saqlandi!",
      reply_markup=main_reply_keyboard(message.from_user.id),
  )


# --- REKLAMA / XABAR TARQATISH (BROADCAST) ---
@router.callback_query(F.data == "broadcast", F.from_user.id == ADMIN_ID)
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
  await state.set_state(BroadcastState.waiting_for_message)
  await callback.message.edit_text(
      "📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (matn,"
      " rasm yoki video) yuboring:"
  )


@router.message(BroadcastState.waiting_for_message, F.from_user.id == ADMIN_ID)
async def broadcast_send(message: Message, state: FSMContext):
  await state.clear()

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM users")
  users = cursor.fetchall()
  conn.close()

  success = 0
  fail = 0

  status_msg = await message.answer("⏳ Xabar tarqatilmoqda...")

  for user in users:
    user_id = user[0]
    try:
      await message.send_copy(chat_id=user_id)
      success += 1
      await asyncio.sleep(0.05)  # Telegram limitiga tushmaslik uchun
    except Exception:
      fail += 1

  await status_msg.edit_text(
      f"✅ Xabar tarqatish yakunlandi!\n\nMuvaffaqiyatli: {success}\nXatolik"
      f" (bloklaganlar): {fail}"
  )


# --- TO'LOVNI TASDIQLASH ---
@router.callback_query(
    F.data.startswith(("approve_", "reject_")), F.from_user.id == ADMIN_ID
)
async def process_payment(callback: CallbackQuery):
  action, payment_id, user_id = callback.data.split("_")
  payment_id = int(payment_id)
  user_id = int(user_id)

  conn = sqlite3.connect("bot_database.db")
  cursor = conn.cursor()
  cursor.execute("SELECT product_type FROM payments WHERE id = ?", (payment_id,))
  res = cursor.fetchone()
  product_type = res[0] if res else ""

  if action == "approve":
    cursor.execute(
        "UPDATE payments SET status = 'approved' WHERE id = ?", (payment_id,)
    )
    conn.commit()
    conn.close()

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n<b>✅ TASDIQLANDI</b>", parse_mode="HTML"
    )

    if "Gemini" in product_type:
      await callback.bot.send_message(
          user_id,
          "🎉 To'lovingiz tasdiqlandi!\n\nIltimos, @"
          f"{ADMIN_USERNAME} ga yozing, u sizga obunani olib beradi.",
          reply_markup=InlineKeyboardMarkup(
              inline_keyboard=[
                  [
                      InlineKeyboardButton(
                          text=f"👤 @{ADMIN_USERNAME} ga yozish",
                          url=f"https://t.me/{ADMIN_USERNAME}",
                      )
                  ]
              ]
          ),
      )
    else:
      channel_link = get_setting("channel_link")
      await callback.bot.send_message(
          user_id,
          f"🎉 To'lovingiz tasdiqlandi! Yopiq kanalga kirish"
          f" havolasi:\n{channel_link}",
      )
  else:
    cursor.execute(
        "UPDATE payments SET status = 'rejected' WHERE id = ?", (payment_id,)
    )
    conn.commit()
    conn.close()

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n<b>❌ RAD ETILDI</b>", parse_mode="HTML"
    )
    await callback.bot.send_message(
        user_id,
        "❌ Afsuski, to'lov chekingiz rad etildi. Iltimos, ma'lumotlarni"
        " tekshirib, qaytadan urinib ko'ring.",
    )


async def main():
  bot = Bot(token=BOT_TOKEN)
  dp = Dispatcher()
  dp.include_router(router)
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
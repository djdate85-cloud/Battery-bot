import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime
import pytz

# --- SOZLAMALAR ---
JSON_FILE = "key.json"
SPREADSHEET_ID = "178ie0Ryq_FwQ0NrA2oL-X3RbkXICndYfLL4Bb4HcO7U"
BOT_TOKEN = "8749296120:AAEeLAmghz_BLK7lr6kAlzqdxk7iDU2zEhA" # O'zingizning tokeningiz

ALLOWED_PHONES = ["+998882855507", "+998770014411"] # Ruxsat etilgan raqamlar
NAMES = ["Umid", "Asqar"]
PARTS = ["Dashbord", "Kontroller", "IoT", "Motor kaleso", "Tormoz", "Gaz pedal", "Batareyka"]
ERRORS = ["10", "11", "12", "13", "14", "15", "16", "18", "19", "21", "22", "23", "24", "26", "27", "31", "32", "35", "37", "39", "40", "41", "50", "51", "52", "54", "55", "57", "58", "Xatolik yo'q"]
COMMENTS = ["Yonmayapti", "O'chib qolgan", "Ishlamayapti", "Singan", "Boshqa"]

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
client = gspread.authorize(creds)

main_sheet = client.open_by_key(SPREADSHEET_ID).sheet1
last_check_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("LastCheck")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class Anketa(StatesGroup):
    ism = State()
    tel = State()
    samokat_num = State()
    qism = State()
    xatolik = State()
    izoh = State()

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="🚀 Botni ishga tushirish"))
    await message.answer("Assalomu alaykum! Ishni boshlash uchun tugmani bosing:", 
                         reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(F.text == "🚀 Botni ishga tushirish")
async def process_begin(message: types.Message, state: FSMContext):
    await state.clear()
    builder = ReplyKeyboardBuilder()
    for name in NAMES: builder.add(types.KeyboardButton(text=name))
    await message.answer("Ismingizni tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(Anketa.ism)

# Ismni cheklash (Faqat ro'yxatdagini qabul qiladi)
@dp.message(Anketa.ism, F.text.in_(NAMES))
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(ism=message.text)
    kb = [[types.KeyboardButton(text="📱 Kontaktni ulash", request_contact=True)]]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=keyboard)
    await state.set_state(Anketa.tel)

@dp.message(Anketa.ism) # Noto'g'ri yozuv kiritilsa
async def wrong_name(message: types.Message):
    await message.answer("Iltimos, tugmalardan birini tanlang!")

@dp.message(Anketa.tel, F.contact)
async def get_tel(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"): phone = "+" + phone
    if phone in ALLOWED_PHONES:
        await state.update_data(tel=phone)
        await message.answer("Samokat raqamini kiriting:", reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(Anketa.samokat_num)
    else:
        await message.answer("Ruxsat berilmagan raqam.")
        await state.clear()

@dp.message(Anketa.samokat_num, F.text) # Samokat raqami qo'lda yoziladi
async def get_scoot(message: types.Message, state: FSMContext):
    await state.update_data(s_num=message.text)
    builder = ReplyKeyboardBuilder()
    for q in PARTS: builder.add(types.KeyboardButton(text=q))
    builder.adjust(2)
    await message.answer("Qism nomini tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(Anketa.qism)

# Qismni cheklash
@dp.message(Anketa.qism, F.text.in_(PARTS))
async def get_part(message: types.Message, state: FSMContext):
    await state.update_data(qism=message.text)
    builder = ReplyKeyboardBuilder()
    for x in ERRORS:
        text = f"{x} xatolik" if x.isdigit() else x
        builder.add(types.KeyboardButton(text=text))
    builder.adjust(4)
    await message.answer("Xatolik kodini tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(Anketa.xatolik)

@dp.message(Anketa.qism)
async def wrong_part(message: types.Message):
    await message.answer("Iltimos, ro'yxatdagi qismlardan birini tanlang!")

# Xatolik kodini cheklash
@dp.message(Anketa.xatolik, F.text.func(lambda txt: any(x in txt for x in ERRORS)))
async def get_error(message: types.Message, state: FSMContext):
    await state.update_data(xatolik=message.text)
    builder = ReplyKeyboardBuilder()
    for i in COMMENTS: builder.add(types.KeyboardButton(text=i))
    builder.adjust(2)
    await message.answer("Mexanik izohini tanlang:", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(Anketa.izoh)

@dp.message(Anketa.xatolik)
async def wrong_error(message: types.Message):
    await message.answer("Iltimos, xatolik kodini tugma orqali tanlang!")

# Izohni cheklash
@dp.message(Anketa.izoh, F.text.in_(COMMENTS))
async def final_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    now = datetime.now(tashkent_tz)
    vagt_str = now.strftime("%d.%m.%Y %H:%M")
    
    samokat_id = data['s_num']
    current_part = data['qism']
    current_error = data['xatolik']
    analysis = "Birinchi marta"

    try:
        cell = last_check_sheet.find(samokat_id)
        if cell:
            last_row = last_check_sheet.row_values(cell.row)
            last_time = tashkent_tz.localize(datetime.strptime(last_row[1], "%d.%m.%Y %H:%M"))
            diff = now - last_time
            muddati = f"{diff.days} kun, {diff.seconds // 3600} soat"
            
            if last_row[2] == current_part and last_row[3] == current_error:
                analysis = f"⚠️ TAKROR (Muddati: {muddati}. Oldin ham {current_part}-{current_error} edi)"
            else:
                analysis = f"Yangi ayb (Muddati: {muddati}. Oldin {last_row[2]}-{last_row[3]} edi)"
            
            last_check_sheet.update(range_name=f"B{cell.row}:D{cell.row}", values=[[vagt_str, current_part, current_error]])
        else:
            last_check_sheet.append_row([samokat_id, vagt_str, current_part, current_error])
    except:
        analysis = "Tahlil qilib bo'lmadi"

    row = [vagt_str, data['ism'], data['tel'], samokat_id, current_part, current_error, message.text, analysis]
    main_sheet.append_row(row, value_input_option="USER_ENTERED")
    
    await message.answer(f"✅ Saqlandi!\n📊 **Tahlil:** {analysis}")
    await message.answer("Navbatdagi samokat raqamini kiriting:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Anketa.samokat_num)

@dp.message(Anketa.izoh)
async def wrong_comment(message: types.Message):
    await message.answer("Iltimos, izohni tugmalar orqali tanlang!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
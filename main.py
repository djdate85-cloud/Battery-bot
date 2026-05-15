import os
import asyncio
import cv2
import numpy as np
import gspread
import logging
from datetime import datetime
from pyzbar.pyzbar import decode
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

# --- KONFIGURATSIYA ---
API_TOKEN = '8671749429:AAENGSHFJmAL8P4cYHFWBiJoIewRyZFiPJE'
ADMIN_ID = 5391864097  
MY_PHONE = '79895811328' 
MIRKOMIL_PHONE = '998935693080'
SHEET_ID = "18urHmsc-Jm2EFHjVDR1nVs-0SzbsFikGDr09pCVlgsU"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

logging.basicConfig(level=logging.INFO)

# --- YORDAMCHI FUNKSIYALAR ---
def get_gsheet_client():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        logging.error(f"GSheet Client Error: {e}")
        return None

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_sheets():
    client = get_gsheet_client()
    if not client:
        logging.error("Google Sheets clientni ishga tushirib bo'lmadi!")
        return
    sh = client.open_by_key(SHEET_ID)
    try:
        battery_sheet = sh.get_worksheet(0)
    except:
        battery_sheet = sh.add_worksheet(title="Batteries", rows="1000", cols="20")
    if not battery_sheet.row_values(1):
        headers = ["id", "Mijoz_ismi_kirish", "Mexanik_ismi_kirish", "Seriya_raqami", "Qabul_qilingan_vaqt", "Muammo", "Adminga_yuborilgan_vaqt", "Skladga_olingan_vaqt", "Skladdan_chiqarilgan_vaqt", "Mexanik_ismi_chiqish", "Mijoz_ismi_chiqish", "Topshirilgan_vaqt", "Seriya_tasdigi", "Remont_soni", "Tarix_eslatmalari", "Qaytarish_muddati", "Model", "Holati", "Tashrif_soni"]
        battery_sheet.insert_row(headers, 1)
    try:
        staff_sheet = sh.get_worksheet(1)
    except:
        staff_sheet = sh.add_worksheet(title="Staff", rows="100", cols="4")
    if not staff_sheet.row_values(1):
        staff_sheet.insert_row(["phone", "chat_id", "role", "full_name"], 1)

def find_battery_row(sn, sheet):
    try:
        cell = sheet.find(str(sn), in_column=4)
        return cell.row
    except:
        return None

async def scan_qr_from_photo(message: types.Message, bot: Bot):
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        nparr = np.frombuffer(file_bytes.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        qr_codes = decode(img)
        return qr_codes[0].data.decode('utf-8') if qr_codes else None
    except Exception as e:
        logging.error(f"QR Scan Error: {e}")
        return None

# --- KLAVIATURALAR ---
def get_customer_menu():
    kb = [[KeyboardButton(text="📥 Batareya topshirish"), KeyboardButton(text="📤 Tayyorini qabul qilish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu():
    kb = [[KeyboardButton(text="📊 Statistika")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_mechanic_menu():
    kb = [[KeyboardButton(text="🛠 Ishlar ro'yxati")], [KeyboardButton(text="➕ Yangi qabul (Remontga)")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_model_keyboard():
    kb = [[KeyboardButton(text="🔋 Wind3"), KeyboardButton(text="🔋 Yandeks")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def problem_menu():
    codes = [5, 20, 21, 22, 23, 24, 60, 61, 62, 64, 65, 77]
    kb = [[KeyboardButton(text=f"{code} xatolik")] for code in codes]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_fail_reasons_kb(sn, model, problem, mech):
    reasons = ["Yonmaydi", "Kuygan", "Ishlamaydi", "Banka ishdan chiqqan", "Plata ishdan chiqqan", "Boshqa sabab"]
    buttons = [[InlineKeyboardButton(text=r, callback_data=f"brk_sel|{sn}|{model}|{r}")] for r in reasons]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_return_count_keyboard():
    buttons, row = [], []
    for i in range(1, 21):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"ret_cnt_{i}"))
        if len(row) == 5: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- STATES ---
class ServiceState(StatesGroup):
    waiting_auth = State()
    choosing_model = State()
    waiting_for_scan = State()
    waiting_problem_type = State()
    mech_remont_model = State()
    mech_remont_scan = State()
    mech_remont_problem = State()
    waiting_fail_reason_text = State()
    waiting_return_model = State()
    cust_bulk_scanning = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
async def save_or_update_battery(sn, model, problem, customer, status):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _save_or_update_sync, sn, model, problem, customer, status)

def _save_or_update_sync(sn, model, problem, customer, status):
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    now_str = get_now()
    duration, v_count = "Birinchi marta", 1
    if row_idx:
        vals = sheet.row_values(row_idx)
        eski_topshirilgan = vals[11] if len(vals) >= 12 else None
        eski_tashrif = int(vals[18]) if len(vals) >= 19 and vals[18] else 0
        v_count = eski_tashrif + 1
        if eski_topshirilgan:
            try:
                d1 = datetime.strptime(eski_topshirilgan, "%Y-%m-%d %H:%M:%S")
                d2 = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
                duration = f"{(d2 - d1).days} kun"
            except: pass
        sheet.update_cell(row_idx, 17, model)
        sheet.update_cell(row_idx, 6, problem)
        sheet.update_cell(row_idx, 2, customer)
        sheet.update_cell(row_idx, 5, now_str)
        sheet.update_cell(row_idx, 18, status)
        sheet.update_cell(row_idx, 16, duration)
        sheet.update_cell(row_idx, 19, v_count)
    else:
        new_row = [""] * 19
        new_row[3], new_row[16], new_row[5], new_row[1], new_row[4], new_row[17], new_row[15], new_row[18] = sn, model, problem, customer, now_str, status, duration, v_count
        sheet.append_row(new_row)
    return v_count, duration

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Xush kelibsiz, Admin! 👑", reply_markup=get_admin_menu())
        return
    client = get_gsheet_client()
    staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
    records = staff_sheet.get_all_records()
    user_role = next((r['role'] for r in records if str(r['chat_id']) == str(message.from_user.id)), None)
    if user_role:
        menu = get_customer_menu() if user_role == 'customer' else get_mechanic_menu()
        await message.answer("Xush kelibsiz!", reply_markup=menu)
    else:
        kb = [[KeyboardButton(text="📱 Kontaktni yuborish", request_contact=True)]]
        await message.answer("Kirish uchun kontaktni yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
        await state.set_state(ServiceState.waiting_auth)

@dp.message(ServiceState.waiting_auth, F.contact)
async def auth_user(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number.replace('+', '')
    role = 'customer' if phone == MY_PHONE else ('mechanic' if phone == MIRKOMIL_PHONE else None)
    if role:
        def save_staff():
            client = get_gsheet_client()
            staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
            staff_sheet.append_row([phone, message.from_user.id, role, message.from_user.full_name])
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, save_staff)
        menu = get_customer_menu() if role == 'customer' else get_mechanic_menu()
        await message.answer(f"Muvaffaqiyatli kirdingiz!", reply_markup=menu)
        await state.clear()
    else:
        await message.answer("Ruxsat berilmadi. ❌")

# --- MIJOZ: BATAREYA TOPSHIRISH ---
@dp.message(F.text == "📥 Batareya topshirish")
async def cust_topshirish_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.choosing_model)

@dp.message(ServiceState.choosing_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def cust_model_sel(message: types.Message, state: FSMContext):
    await state.update_data(c_model=message.text)
    await message.answer(f"📸 {message.text} SN skanerlang.")
    await state.set_state(ServiceState.waiting_for_scan)

@dp.message(ServiceState.waiting_for_scan, F.photo)
async def cust_scan_proc(message: types.Message, state: FSMContext):
    sn = await scan_qr_from_photo(message, bot)
    if not sn:
        await message.answer("❌ QR o'qilmadi. Qayta urinib ko'ring.")
        return
    await state.update_data(c_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu())
    await state.set_state(ServiceState.waiting_problem_type)

@dp.message(ServiceState.waiting_problem_type)
async def cust_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_cnt, dur = await save_or_update_battery(data['c_sn'], data['c_model'], message.text, message.from_user.full_name, 'Kutilmoqda')
    await message.answer(f"✅ Qabul qilindi.\n🔄 Tashrif: {v_cnt}\n⏱ Muddat: {dur}", reply_markup=get_customer_menu())
    await state.clear()

# --- MEXANIK: REMONTGA YUBORISH ---
@dp.message(F.text == "➕ Yangi qabul (Remontga)")
async def mech_remont_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.mech_remont_model)

@dp.message(ServiceState.mech_remont_model)
async def mech_remont_model_sel(message: types.Message, state: FSMContext):
    await state.update_data(m_model=message.text)
    await message.answer(f"📸 {message.text} SN skanerlang.")
    await state.set_state(ServiceState.mech_remont_scan)

@dp.message(ServiceState.mech_remont_scan, F.photo)
async def mech_remont_scan_proc(message: types.Message, state: FSMContext):
    sn = await scan_qr_from_photo(message, bot)
    if not sn:
        await message.answer("❌ QR o'qilmadi. Qayta urinib ko'ring.")
        return
    await state.update_data(m_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu())
    await state.set_state(ServiceState.mech_remont_problem)

@dp.message(ServiceState.mech_remont_problem)
async def mech_remont_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sn, model, problem = data['m_sn'], data['m_model'], message.text
    mech_name = message.from_user.full_name
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ REMONT BITDI", callback_data=f"rep_fin|{sn}|{model}|{problem}|{mech_name}")],
        [InlineKeyboardButton(text="❌ BRAK (Remont bo'lmadi)", callback_data=f"rep_brk|{sn}|{model}|{problem}|{mech_name}")]
    ])
    await bot.send_message(ADMIN_ID, f"🛠 **YANGI REMONT SO'ROVI!**\n\n🆔 SN: `{sn}`\n📦 Model: {model}\n⚠️ Xato: {problem}\n👤 Mexanik: {mech_name}", reply_markup=kb)
    await message.answer(f"✅ SN `{sn}` Adminga yuborildi.", reply_markup=get_mechanic_menu())
    await state.clear()

# --- ADMIN: REMONT BITGANDA YOKI BRAK BO'LGANDA ---
@dp.callback_query(F.data.startswith("rep_fin|"))
async def admin_remont_ok(callback: types.CallbackQuery):
    await callback.answer("⏳ Saqlanmoqda...")
    _, sn, model, problem, mech_name = callback.data.split("|")
    def sync_save():
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        new_row = [""] * 19
        new_row[3], new_row[16], new_row[5], new_row[2], new_row[17], new_row[7], new_row[13], new_row[18] = sn, model, problem, mech_name, "Tayyor", get_now(), "1", "1"
        sheet.append_row(new_row)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_save)
    await callback.message.edit_text(f"✅ SN: `{sn}` TAYYOR holatida saqlandi.")

@dp.callback_query(F.data.startswith("rep_brk|"))
async def admin_remont_fail(callback: types.CallbackQuery):
    await callback.answer()
    _, sn, model, problem, mech_name = callback.data.split("|")
    await callback.message.edit_text(f"❌ SN: `{sn}` uchun brak sababini tanlang:", reply_markup=get_fail_reasons_kb(sn, model, problem, mech_name))

@dp.callback_query(F.data.startswith("brk_sel|"))
async def admin_brak_final(callback: types.CallbackQuery, state: FSMContext):
    _, sn, model, reason = callback.data.split("|")
    if reason == "Boshqa sabab":
        await callback.answer()
        await state.update_data(tmp_sn=sn, tmp_mod=model)
        await callback.message.answer("Brak sababini yozib yuboring:")
        await state.set_state(ServiceState.waiting_fail_reason_text)
        return
    await callback.answer("⏳ Saqlanmoqda...")
    def sync_save_brak():
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        new_row = [""] * 19
        new_row[3], new_row[16], new_row[17], new_row[14], new_row[9], new_row[18] = sn, model, "Brak", reason, get_now(), "1"
        sheet.append_row(new_row)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_save_brak)
    await callback.message.edit_text(f"🗑 SN: `{sn}` BRAK ({reason}) sifatida saqlandi.")

@dp.message(ServiceState.waiting_fail_reason_text)
async def admin_brak_custom_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    def sync_save_custom():
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        new_row = [""] * 19
        new_row[3], new_row[16], new_row[17], new_row[14], new_row[9], new_row[18] = data['tmp_sn'], data['tmp_mod'], "Brak", message.text, get_now(), "1"
        sheet.append_row(new_row)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, sync_save_custom)
    await message.answer(f"🗑 SN: `{data['tmp_sn']}` BRAK ({message.text}) sifatida saqlandi.")
    await state.clear()

# --- MIJOZ: TAYYORINI QABUL QILISH ---
@dp.message(F.text == "📤 Tayyorini qabul qilish")
async def cust_bulk_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.waiting_return_model)

@dp.message(ServiceState.waiting_return_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def cust_bulk_count(message: types.Message, state: FSMContext):
    await message.answer(f"Nechta batareya qabul qilasiz?", reply_markup=get_return_count_keyboard())

@dp.callback_query(F.data.startswith("ret_cnt_"))
async def cust_bulk_init(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2])
    await state.update_data(c_t=cnt, c_s=0, scanned_sns=[])
    await callback.answer()
    await callback.message.answer(f"1/{cnt} - Skanerlang:")
    await state.set_state(ServiceState.cust_bulk_scanning)

@dp.message(ServiceState.cust_bulk_scanning, F.photo)
async def cust_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target, scanned, already = data['c_t'], data['c_s'], data.get('scanned_sns', [])
    sn = await scan_qr_from_photo(message, bot)
    if not sn or sn in already:
        await message.answer("❌ QR xato yoki allaqachon skanerlangan.")
        return
    def finalize_cust():
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        row = find_battery_row(sn, sheet)
        if row and sheet.cell(row, 18).value == 'Tayyor':
            sheet.update_cell(row, 18, 'Topshirildi')
            sheet.update_cell(row, 11, message.from_user.full_name)
            sheet.update_cell(row, 12, get_now())
            return True
        return False
    loop = asyncio.get_event_loop()
    if await loop.run_in_executor(None, finalize_cust):
        scanned += 1
        already.append(sn)
        await state.update_data(c_s=scanned, scanned_sns=already)
        if scanned < target:
            await message.answer(f"✅ {scanned}/{target} qabul qilindi. Keyingisi:")
        else:
            await message.answer("🏁 Barcha batareyalar topshirildi!", reply_markup=get_customer_menu())
            await state.clear()
    else:
        await message.answer("❌ Bu SN tayyor emas yoki topilmadi.")

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    def get_s():
        return get_gsheet_client().open_by_key(SHEET_ID).get_worksheet(0).get_all_records()
    loop = asyncio.get_event_loop()
    recs = await loop.run_in_executor(None, get_s)
    stats = {}
    for r in recs:
        h = r.get('Holati', 'Noma’lum')
        stats[h] = stats.get(h, 0) + 1
    res = "📊 Statistika:\n" + "\n".join([f"- {s}: {c}" for s, c in stats.items()])
    await message.answer(res)

async def main():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, init_sheets)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
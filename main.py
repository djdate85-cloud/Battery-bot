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
    creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", SCOPE)
    return gspread.authorize(creds)

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_sheets():
    client = get_gsheet_client()
    sh = client.open_by_key(SHEET_ID)
    
    # Batteries sheet setup
    try:
        battery_sheet = sh.get_worksheet(0)
    except:
        battery_sheet = sh.add_worksheet(title="Batteries", rows="1000", cols="20")
    
    if not battery_sheet.row_values(1):
        headers = [
            "id", "Mijoz_ismi_kirish", "Mexanik_ismi_kirish", "Seriya_raqami", 
            "Qabul_qilingan_vaqt", "Muammo", "Adminga_yuborilgan_vaqt", 
            "Skladga_olingan_vaqt", "Skladdan_chiqarilgan_vaqt", "Mexanik_ismi_chiqish", 
            "Mijoz_ismi_chiqish", "Topshirilgan_vaqt", "Seriya_tasdigi", 
            "Remont_soni", "Tarix_eslatmalari", "Qaytarish_muddati", "Model", 
            "Holati", "Tashrif_soni"
        ]
        battery_sheet.insert_row(headers, 1)

    # Staff sheet setup
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
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    qr_codes = decode(img)
    return qr_codes[0].data.decode('utf-8') if qr_codes else None

# --- KLAVIATURALAR ---
def get_customer_menu():
    kb = [[KeyboardButton(text="📥 Batareya topshirish"), KeyboardButton(text="📤 Tayyorini qabul qilish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu():
    kb = [[KeyboardButton(text="📊 Statistika")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_mechanic_menu():
    kb = [[KeyboardButton(text="🛠 Ishlar ro'yxati")], [KeyboardButton(text="➕ Yangi qabul (Skaner)")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_model_keyboard():
    kb = [[KeyboardButton(text="🔋 Wind3"), KeyboardButton(text="🔋 Yandeks")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def problem_menu():
    codes = [5, 20, 21, 22, 23, 24, 60, 61, 62, 64, 65, 77]
    kb = [[KeyboardButton(text=f"{code} xatolik")] for code in codes]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_fail_reasons_kb(sn):
    reasons = ["Banka ishdan chiqqan", "Suvga tushgan", "Plata kuygan", "Razyom kuygan", "Boshqa"]
    buttons = [[InlineKeyboardButton(text=r, callback_data=f"f_r_{sn}_{r}")] for r in reasons]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_return_count_keyboard():
    buttons, row = [], []
    for i in range(1, 21):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"ret_cnt_{i}"))
        if len(row) == 5: 
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- STATES ---
class ServiceState(StatesGroup):
    waiting_auth = State()
    choosing_model = State()
    waiting_for_scan = State()
    waiting_problem_type = State()
    mech_receiving_scan = State() 
    mech_receiving_problem = State() 
    waiting_fail_reason = State()
    waiting_return_model = State()
    mech_bulk_scanning = State()
    cust_bulk_scanning = State()
    mech_direct_model = State()
    mech_direct_scan = State()
    mech_direct_problem = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
async def save_or_update_battery(sn, model, problem, customer, status):
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
        new_row[3], new_row[16], new_row[5], new_row[1], new_row[4], new_row[17], new_row[15], new_row[18] = \
            sn, model, problem, customer, now_str, status, duration, v_count
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
        client = get_gsheet_client()
        staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
        staff_sheet.append_row([phone, message.from_user.id, role, message.from_user.full_name])
        menu = get_customer_menu() if role == 'customer' else get_mechanic_menu()
        await message.answer(f"Muvaffaqiyatli kirdingiz!", reply_markup=menu)
        await state.clear()
    else:
        await message.answer("Ruxsat berilmadi. ❌")

# --- MEXANIK: DIRECT QABUL ---
@dp.message(F.text == "➕ Yangi qabul (Skaner)")
async def mech_direct_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.mech_direct_model)

@dp.message(ServiceState.mech_direct_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def mech_direct_model_sel(message: types.Message, state: FSMContext):
    await state.update_data(m_dir_model=message.text)
    await message.answer(f"📸 {message.text} SN skanerlang.")
    await state.set_state(ServiceState.mech_direct_scan)

@dp.message(ServiceState.mech_direct_scan, F.photo)
async def mech_direct_scan_proc(message: types.Message, state: FSMContext):
    sn = await scan_qr_from_photo(message, bot)
    if not sn:
        await message.answer("❌ O'qilmadi.")
        return
    await state.update_data(m_dir_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu())
    await state.set_state(ServiceState.mech_direct_problem)

@dp.message(ServiceState.mech_direct_problem)
async def mech_direct_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_cnt, dur = await save_or_update_battery(data['m_dir_sn'], data['m_dir_model'], message.text, "Direct Scan", "Skladga olindi")
    
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(data['m_dir_sn'], sheet)
    if row_idx:
        sheet.update_cell(row_idx, 3, message.from_user.full_name)
        
    await message.answer(f"✅ Skladga olindi.\n🔄 Kelish: {v_cnt}\n⏱ Muddat: {dur}", reply_markup=get_mechanic_menu())
    await state.clear()

# --- MEXANIK: ISHLAR RO'YXATI ---
@dp.message(F.text == "🛠 Ishlar ro'yxati")
async def mech_work_list(message: types.Message):
    client = get_gsheet_client()
    records = client.open_by_key(SHEET_ID).get_worksheet(0).get_all_records()
    jobs = [r for r in records if r.get('Holati') == 'Skladga olindi']
    
    if not jobs:
        await message.answer("Hozircha ish yo'q.")
        return
        
    for r in jobs:
        sn = r['Seriya_raqami']
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛠 Remontga yuborish", callback_data=f"m_rep_{sn}")]])
        await message.answer(f"🔋 {r['Model']}\nSN: `{sn}`\nXato: {r['Muammo']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("m_rep_"))
async def m_rep_to_adm(callback: types.CallbackQuery):
    sn = callback.data.replace("m_rep_", "")
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    
    if row_idx:
        sheet.update_cell(row_idx, 18, 'Remontda')
        sheet.update_cell(row_idx, 7, get_now())
        vals = sheet.row_values(row_idx)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Remont bo'ldi", callback_data=f"a_ok_{sn}")],
            [InlineKeyboardButton(text="❌ Remont bo'lmadi", callback_data=f"a_no_{sn}")]
        ])
        
        await bot.send_message(ADMIN_ID, f"🛠 **Remont so'rovi!**\n🆔 SN: `{sn}`\n⚠️ Xato: {vals[5]}", reply_markup=kb)
        await callback.message.edit_text(f"✅ `{sn}` Adminga yuborildi.")
    await callback.answer()

# --- ADMIN: TASDIQLASH ---
@dp.callback_query(F.data.startswith("a_ok_"))
async def adm_rep_ok(callback: types.CallbackQuery):
    sn = callback.data.replace("a_ok_", "")
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    
    if row_idx:
        curr_remont = int(sheet.cell(row_idx, 14).value or 0)
        sheet.update_cell(row_idx, 18, 'Tayyor')
        sheet.update_cell(row_idx, 8, get_now())
        sheet.update_cell(row_idx, 14, curr_remont + 1)
        await callback.message.edit_text(f"✅ `{sn}` Tayyor skladga o'tdi.")
    await callback.answer()

@dp.callback_query(F.data.startswith("a_no_"))
async def adm_rep_no(callback: types.CallbackQuery):
    sn = callback.data.replace("a_no_", "")
    await callback.message.edit_text(f"❌ Rad etish sababi:", reply_markup=get_fail_reasons_kb(sn))
    await callback.answer()

@dp.callback_query(F.data.startswith("f_r_"))
async def save_fail_reason(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.replace("f_r_", "").split("_", 1)
    sn, reason = parts[0], parts[1]
    
    if reason == "Boshqa":
        await state.update_data(fail_sn=sn)
        await callback.message.answer("Sababni yozing:")
        await state.set_state(ServiceState.waiting_fail_reason)
    else:
        client = get_gsheet_client()
        sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
        row_idx = find_battery_row(sn, sheet)
        if row_idx:
            sheet.update_cell(row_idx, 18, 'Brak')
            sheet.update_cell(row_idx, 9, get_now())
            sheet.update_cell(row_idx, 15, reason)
            await callback.message.edit_text(f"🗑 `{sn}` brak qilindi.")
    await callback.answer()

# --- MIJOZ: TOPSHIRISH ---
@dp.message(F.text == "📥 Batareya topshirish")
async def start_sub(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.choosing_model)

@dp.message(ServiceState.choosing_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def sel_model_cust(message: types.Message, state: FSMContext):
    await state.update_data(c_model=message.text)
    await message.answer(f"📸 SN skanerlang.")
    await state.set_state(ServiceState.waiting_for_scan)

@dp.message(ServiceState.waiting_for_scan, F.photo)
async def handle_scan_cust(message: types.Message, state: FSMContext):
    sn = await scan_qr_from_photo(message, bot)
    if not sn:
        await message.answer("❌ O'qilmadi.")
        return
    await state.update_data(c_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu())
    await state.set_state(ServiceState.waiting_problem_type)

@dp.message(ServiceState.waiting_problem_type)
async def set_prob_cust(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prob = message.text
    v_cnt, dur = await save_or_update_battery(data['c_sn'], data['c_model'], prob, message.from_user.full_name, 'Kutilmoqda')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛠 Yo'naltirish", callback_data=f"adm_to_mec_{data['c_sn']}")]])
    
    admin_msg = (
        f"📥 **Yangi batareya topshirildi!**\n\n"
        f"🆔 SN: `{data['c_sn']}`\n"
        f"🔋 Model: {data['c_model']}\n"
        f"⚠️ **Xatolik: {prob}**\n"
        f"🔄 Kelish: {v_cnt}\n"
        f"⏱ Muddat: {dur}"
    )
    
    await bot.send_message(ADMIN_ID, admin_msg, reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Adminga yuborildi.", reply_markup=get_customer_menu())
    await state.clear()

# --- ADMIN TO MEXANIK ---
@dp.callback_query(F.data.startswith("adm_to_mec_"))
async def adm_to_mec(callback: types.CallbackQuery):
    sn = callback.data.split("_")[3]
    client = get_gsheet_client()
    staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
    records = staff_sheet.get_all_records()
    mech_chat_id = next((r['chat_id'] for r in records if str(r['phone']) == MIRKOMIL_PHONE), None)
    
    if mech_chat_id:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Qabul", callback_data=f"m_rec_{sn}")]])
        await bot.send_message(mech_chat_id, f"🔔 Yangi SN: `{sn}`", reply_markup=kb)
        await callback.message.edit_text(f"✅ SN: `{sn}` - Mexanikka yo'naltirildi.")
    else:
        await callback.message.edit_text("❌ Mexanik topilmadi.")
    
    await callback.answer()

@dp.callback_query(F.data.startswith("m_rec_"))
async def mech_rec_start(callback: types.CallbackQuery, state: FSMContext):
    sn = callback.data.split("_")[2]
    await state.update_data(m_sn=sn)
    await callback.message.answer(f"📸 `{sn}`ni tasdiqlash uchun skanerlang.")
    await state.set_state(ServiceState.mech_receiving_scan)
    await callback.answer()

@dp.message(ServiceState.mech_receiving_scan, F.photo)
async def mech_rec_scan_finish(message: types.Message, state: FSMContext):
    sn = await scan_qr_from_photo(message, bot)
    if not sn: 
        await message.answer("❌ QR kod o'qilmadi. Qayta urinib ko'ring.")
        return
    
    data = await state.get_data()
    if sn == data['m_sn']:
        await message.answer(f"✅ SN tasdiqlandi: `{sn}`.\nXato kodini aniqlang:", reply_markup=problem_menu())
        await state.set_state(ServiceState.mech_receiving_problem)
    else:
        await message.answer(f"❌ Xato SN skanerlandi. `{data['m_sn']}` kutilmoqda.")

@dp.message(ServiceState.mech_receiving_problem)
async def mech_rec_finish_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    sn = data['m_sn']
    prob = message.text
    
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    
    if row_idx:
        sheet.update_cell(row_idx, 18, 'Skladga olindi')
        sheet.update_cell(row_idx, 3, message.from_user.full_name)
        sheet.update_cell(row_idx, 6, prob) 
        sheet.update_cell(row_idx, 8, get_now()) 
        
    await message.answer(f"✅ SN `{sn}` xato kodi ({prob}) bilan skladga olindi.", reply_markup=get_mechanic_menu())
    await state.clear()

# --- BULK PROCESS (OLIB KETISH) ---
@dp.message(F.text == "📤 Tayyorini qabul qilish")
async def bulk_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.waiting_return_model)

@dp.message(ServiceState.waiting_return_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def bulk_count(message: types.Message, state: FSMContext):
    await state.update_data(ret_mod=message.text)
    await message.answer(f"Nechta?", reply_markup=get_return_count_keyboard())

@dp.callback_query(F.data.startswith("ret_cnt_"))
async def bulk_adm_req(callback: types.CallbackQuery, state: FSMContext):
    cnt = callback.data.split("_")[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ruxsat", callback_data=f"adm_bulk_ok_{cnt}")]])
    await bot.send_message(ADMIN_ID, f"🎁 Mijoz {cnt} ta olmoqchi.", reply_markup=kb)
    await callback.message.edit_text("⏳ Kutilmoqda...")
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_bulk_ok_"))
async def adm_bulk_approve(callback: types.CallbackQuery):
    cnt = callback.data.split("_")[3]
    client = get_gsheet_client()
    staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
    mech_chat_id = next((r['chat_id'] for r in staff_sheet.get_all_records() if str(r['phone']) == MIRKOMIL_PHONE), None)
    
    if mech_chat_id:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"m_bulk_{cnt}")]])
        await bot.send_message(mech_chat_id, f"🎁 {cnt} ta chiqaring.", reply_markup=kb)
    await callback.message.edit_text("✅ Tasdiqlandi.")
    await callback.answer()

@dp.callback_query(F.data.startswith("m_bulk_"))
async def m_bulk_scan_init(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2])
    # scanned_sns - skanerlanganlarni saqlash uchun yangi ro'yxat
    await state.update_data(b_t=cnt, b_s=0, scanned_sns=[]) 
    await callback.message.answer(f"1/{cnt} - Skanerlang:")
    await state.set_state(ServiceState.mech_bulk_scanning)
    await callback.answer()

@dp.message(ServiceState.mech_bulk_scanning, F.photo)
async def m_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target, scanned = data['b_t'], data['b_s']
    already_scanned = data.get('scanned_sns', [])
    
    sn = await scan_qr_from_photo(message, bot)
    if not sn: 
        await message.answer("❌ QR kod o'qilmadi.")
        return

    # Takroriylikni tekshirish
    if sn in already_scanned:
        await message.answer(f"⚠️ `{sn}` allaqachon skanerlandi! Keyingisini yuboring.")
        return
    
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    
    if row_idx and sheet.cell(row_idx, 18).value == 'Tayyor':
        sheet.update_cell(row_idx, 18, 'Yuborilmoqda')
        sheet.update_cell(row_idx, 10, message.from_user.full_name)
        sheet.update_cell(row_idx, 13, sn)
        scanned += 1
        already_scanned.append(sn)
        await state.update_data(b_s=scanned, scanned_sns=already_scanned)
        
        if scanned < target:
            await message.answer(f"✅ {scanned}/{target} skanerlandi. Keyingisi:")
        else:
            staff_sheet = client.open_by_key(SHEET_ID).get_worksheet(1)
            cust_chat_id = next((r['chat_id'] for r in staff_sheet.get_all_records() if str(r['phone']) == MY_PHONE), None)
            if cust_chat_id:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"c_bulk_{target}")]])
                await bot.send_message(cust_chat_id, "🎁 Qabul qiling:", reply_markup=kb)
            await message.answer("✅ Hammasi skanerlandi.")
            await state.clear()
    else:
        await message.answer("❌ Bu SN tayyor emas yoki bazada yo'q!")

@dp.callback_query(F.data.startswith("c_bulk_"))
async def c_bulk_init(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2])
    await state.update_data(c_t=cnt, c_s=0, scanned_sns=[])
    await callback.message.answer(f"1/{cnt} - Skanerlang:")
    await state.set_state(ServiceState.cust_bulk_scanning)
    await callback.answer()

@dp.message(ServiceState.cust_bulk_scanning, F.photo)
async def c_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target, scanned = data['c_t'], data['c_s']
    already_scanned = data.get('scanned_sns', [])
    
    sn = await scan_qr_from_photo(message, bot)
    if not sn: 
        await message.answer("❌ QR kod o'qilmadi.")
        return

    if sn in already_scanned:
        await message.answer(f"⚠️ `{sn}` allaqachon skanerlandi!")
        return
    
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn, sheet)
    
    if row_idx:
        # Faqat yuborilayotgan batareyalarni qabul qilish mantiqi
        curr_status = sheet.cell(row_idx, 18).value
        if curr_status == 'Yuborilmoqda':
            sheet.update_cell(row_idx, 18, 'Topshirildi')
            sheet.update_cell(row_idx, 11, message.from_user.full_name)
            sheet.update_cell(row_idx, 12, get_now())
            scanned += 1
            already_scanned.append(sn)
            await state.update_data(c_s=scanned, scanned_sns=already_scanned)
            
            if scanned < target:
                await message.answer(f"✅ {scanned}/{target} qabul qilindi. Keyingisi:")
            else:
                await message.answer("🏁 Barcha batareyalar qabul qilindi!", reply_markup=get_customer_menu())
                await state.clear()
        else:
            await message.answer(f"❌ Bu batareya statusi: {curr_status}. Uni qabul qilib bo'lmaydi.")
    else:
        await message.answer("❌ Bunday seriya raqami topilmadi!")

# --- ADMIN: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    client = get_gsheet_client()
    records = client.open_by_key(SHEET_ID).get_worksheet(0).get_all_records()
    stats = {}
    for r in records:
        h = r.get('Holati', 'Noma’lum')
        stats[h] = stats.get(h, 0) + 1
    
    res = "📊 Statistika:\n"
    for s, c in stats.items():
        res += f"- {s}: {c}\n"
    await message.answer(res)

if __name__ == '__main__':
    init_sheets()
    asyncio.run(dp.start_polling(bot))
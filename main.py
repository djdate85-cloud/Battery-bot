import os
import asyncio
import cv2
import numpy as np
import gspread
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

# --- SOZLAMALAR ---
API_TOKEN = '8671749429:AAENGSHFJmAL8P4cYHFWBiJoIewRyZFiPJE'
ADMIN_ID = 5391864097  
MY_PHONE = '79895811328' 
MIRKOMIL_PHONE = '998935693080' 

# --- GOOGLE SHEETS SOZLAMALARI ---
SHEET_ID = "18urHmsc-Jm2EFHjVDR1nVs-0SzbsFikGDr09pCVlgsU" # Rasmga asosan
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("key.json", SCOPE)
CLIENT = gspread.authorize(CREDS)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- JADVALNI TAYYORLASH (Lokal bazani init_db o'rniga) ---
def init_sheets():
    try:
        sh = CLIENT.open_by_key(SHEET_ID)
        # 1-varaq: Batareyalar (batteries jadvali o'rniga)
        battery_sheet = sh.get_worksheet(0)
        if not battery_sheet.row_values(1):
            headers = [
                "ID", "Mijoz_ismi_kirish", "Mexanik_ismi_kirish", "Seriya_raqami", 
                "Qabul_qilingan_vaqt", "Muammo", "Adminga_yuborilgan_vaqt", 
                "Skladga_olingan_vaqt", "Skladdan_chiqarilgan_vaqt", "Mexanik_ismi_chiqish", 
                "Mijoz_ismi_chiqish", "Topshirilgan_vaqt", "Seriya_tasdigi", 
                "Remont_soni", "Tarix_eslatmalari", "Qaytarish_muddati", "Model", 
                "Holati", "Tashrif_soni"
            ]
            battery_sheet.insert_row(headers, 1)
        
        # 2-varaq: Xodimlar (staff jadvali o'rniga)
        try:
            staff_sheet = sh.get_worksheet(1)
        except:
            staff_sheet = sh.add_worksheet(title="Staff", rows="100", cols="4")
            
        if not staff_sheet.row_values(1):
            staff_sheet.insert_row(["phone", "chat_id", "role", "full_name"], 1)
            
    except Exception as e:
        print(f"Xatolik: {e}. Google Sheets ruxsatlarini tekshiring!")

init_sheets()

class ServiceState(StatesGroup):
    waiting_auth = State()
    choosing_model = State()
    waiting_for_scan = State()
    waiting_problem_type = State()
    mech_receiving_scan = State() 
    waiting_fail_reason = State()
    waiting_return_model = State()
    mech_bulk_scanning = State()
    cust_bulk_scanning = State()
    mech_direct_model = State()
    mech_direct_scan = State()
    mech_direct_problem = State()

# --- YORDAMCHI FUNKSIYALAR ---
def get_staff_role(chat_id):
    try:
        staff_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(1)
        records = staff_sheet.get_all_records()
        for row in records:
            if str(row['chat_id']) == str(chat_id):
                return row['role']
    except: pass
    return None

def find_battery_row(sn):
    try:
        battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
        cell = battery_sheet.find(sn, in_column=4) # Seriya_raqami 4-ustun
        return cell.row if cell else None
    except: return None

# --- KLAVIATURALAR (O'zgartirilmagan) ---
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
    buttons = []
    row = []
    for i in range(1, 21):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"ret_cnt_{i}"))
        if len(row) == 5: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- AUTH ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Xush kelibsiz, Admin! 👑", reply_markup=get_admin_menu())
        return
    role = get_staff_role(message.from_user.id)
    if role:
        menu = get_customer_menu() if role == 'customer' else get_mechanic_menu()
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
        staff_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(1)
        staff_sheet.append_row([phone, message.from_user.id, role, message.from_user.full_name])
        menu = get_customer_menu() if role == 'customer' else get_mechanic_menu()
        await message.answer(f"Muvaffaqiyatli kirdingiz!", reply_markup=menu)
        await state.clear()
    else:
        await message.answer("Ruxsat berilmadi. ❌")

# --- QABUL MANTIQI ---
async def save_or_update_battery(sn, model, problem, customer, status):
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    now_str = get_now()
    duration = "Birinchi marta"
    v_count = 1

    if row_idx:
        all_vals = battery_sheet.row_values(row_idx)
        # Topshirilgan_vaqt (12-ustun), Tashrif_soni (19-ustun)
        last_time = all_vals[11] if len(all_vals) >= 12 else None
        v_count = (int(all_vals[18]) if len(all_vals) >= 19 and all_vals[18] else 0) + 1
        if last_time:
            try:
                d1 = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                d2 = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
                duration = f"{(d2-d1).days} kun"
            except: pass
        
        # Update
        battery_sheet.update_cell(row_idx, 17, model)   # Model (17)
        battery_sheet.update_cell(row_idx, 6, problem)  # Muammo (6)
        battery_sheet.update_cell(row_idx, 2, customer) # Mijoz_ismi_k (2)
        battery_sheet.update_cell(row_idx, 5, now_str)  # Qabul_v (5)
        battery_sheet.update_cell(row_idx, 18, status)  # Holati (18)
        battery_sheet.update_cell(row_idx, 16, duration)# Qaytarish_m (16)
        battery_sheet.update_cell(row_idx, 19, v_count) # Tashrif_s (19)
    else:
        new_row = [""] * 19
        new_row[1], new_row[3], new_row[4], new_row[5] = customer, sn, now_str, problem
        new_row[15], new_row[16], new_row[17], new_row[18] = duration, model, status, v_count
        battery_sheet.append_row(new_row)
    
    return v_count, duration

# --- MEXANIK: DIRECT ---
@dp.message(F.text == "➕ Yangi qabul (Skaner)")
async def mech_direct_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard())
    await state.set_state(ServiceState.mech_direct_model)

@dp.message(ServiceState.mech_direct_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def mech_direct_model_sel(message: types.Message, state: FSMContext):
    await state.update_data(m_dir_model=message.text)
    await message.answer(f"📸 {message.text} SN skanerlang."); await state.set_state(ServiceState.mech_direct_scan)

@dp.message(ServiceState.mech_direct_scan, F.photo)
async def mech_direct_scan_proc(message: types.Message, state: FSMContext):
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: await message.answer("❌ O'qilmadi."); return
    sn = codes[0].data.decode('utf-8'); await state.update_data(m_dir_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu()); await state.set_state(ServiceState.mech_direct_problem)

@dp.message(ServiceState.mech_direct_problem)
async def mech_direct_finish(message: types.Message, state: FSMContext):
    data = await state.get_data(); sn = data['m_dir_sn']
    v_cnt, dur = await save_or_update_battery(sn, data['m_dir_model'], message.text, "Direct Scan", "Skladga olindi")
    
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        battery_sheet.update_cell(row_idx, 3, message.from_user.full_name) # Mexanik_ismi_kirish (3)

    await message.answer(f"✅ Skladga olindi.\n🔄 Kelish: {v_cnt}\n⏱ Muddat: {dur}", reply_markup=get_mechanic_menu())
    await state.clear()

# --- ISHLAR RO'YXATI ---
@dp.message(F.text == "🛠 Ishlar ro'yxati")
async def mech_work_list(message: types.Message):
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    records = battery_sheet.get_all_records()
    jobs = [r for r in records if r['Holati'] == 'Skladga olindi']
    if not jobs: await message.answer("Hozircha ish yo'q."); return
    for r in jobs:
        sn = r['Seriya_raqami']
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛠 Remontga yuborish", callback_data=f"m_rep_{sn}")]])
        await message.answer(f"🔋 {r['Model']}\nSN: `{sn}`\nXato: {r['Muammo']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("m_rep_"))
async def m_rep_to_adm(callback: types.CallbackQuery):
    sn = callback.data.replace("m_rep_", "")
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        battery_sheet.update_cell(row_idx, 18, 'Remontda')
        battery_sheet.update_cell(row_idx, 7, get_now()) # Adminga_yuborilgan_vaqt (7)
        r = battery_sheet.row_values(row_idx)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Remont bo'ldi", callback_data=f"a_ok_{sn}")],
            [InlineKeyboardButton(text="❌ Remont bo'lmadi", callback_data=f"a_no_{sn}")]
        ])
        await bot.send_message(ADMIN_ID, f"🛠 **Remont so'rovi!**\n🆔 SN: `{sn}`\n⚠️ Xato: {r[5]}", reply_markup=kb)
        await callback.message.edit_text(f"✅ `{sn}` Adminga yuborildi."); await callback.answer()

# --- ADMIN QARORI ---
@dp.callback_query(F.data.startswith("a_ok_"))
async def adm_rep_ok(callback: types.CallbackQuery):
    sn = callback.data.replace("a_ok_", "")
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        rem_count = int(battery_sheet.cell(row_idx, 14).value or 0)
        battery_sheet.update_cell(row_idx, 18, 'Tayyor')
        battery_sheet.update_cell(row_idx, 8, get_now()) # Skladga_olingan_vaqt (8)
        battery_sheet.update_cell(row_idx, 14, rem_count + 1) # Remont_soni (14)
        await callback.message.edit_text(f"✅ `{sn}` Tayyor skladga o'tdi."); await callback.answer()

@dp.callback_query(F.data.startswith("a_no_"))
async def adm_rep_no(callback: types.CallbackQuery):
    sn = callback.data.replace("a_no_", "")
    await callback.message.edit_text(f"❌ Rad etish sababi:", reply_markup=get_fail_reasons_kb(sn)); await callback.answer()

@dp.callback_query(F.data.startswith("f_r_"))
async def save_fail_reason(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.replace("f_r_", "").split("_", 1); sn, reason = data[0], data[1]
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        battery_sheet.update_cell(row_idx, 18, 'Brak')
        battery_sheet.update_cell(row_idx, 9, get_now()) # Skladdan_chiqarilgan_vaqt (9)
        battery_sheet.update_cell(row_idx, 15, reason)   # Tarix_eslatmalari (15)
        await callback.message.edit_text(f"🗑 `{sn}` brak qilindi."); await callback.answer()

# --- MIJOZ TOPSHIRISH (O'zgartirilmagan) ---
@dp.message(F.text == "📥 Batareya topshirish")
async def start_sub(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard()); await state.set_state(ServiceState.choosing_model)

@dp.message(ServiceState.choosing_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def sel_model(message: types.Message, state: FSMContext):
    await state.update_data(c_model=message.text); await message.answer(f"📸 SN skanerlang."); await state.set_state(ServiceState.waiting_for_scan)

@dp.message(ServiceState.waiting_for_scan, F.photo)
async def handle_scan(message: types.Message, state: FSMContext):
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: await message.answer("❌ O'qilmadi."); return
    sn = codes[0].data.decode('utf-8'); await state.update_data(c_sn=sn)
    await message.answer(f"✅ SN: `{sn}`. Xato turi:", reply_markup=problem_menu()); await state.set_state(ServiceState.waiting_problem_type)

@dp.message(ServiceState.waiting_problem_type)
async def set_prob(message: types.Message, state: FSMContext):
    data = await state.get_data()
    v_cnt, dur = await save_or_update_battery(data['c_sn'], data['c_model'], message.text, message.from_user.full_name, 'Kutilmoqda')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛠 Yo'naltirish", callback_data=f"adm_to_mec_{data['c_sn']}")]])
    await bot.send_message(ADMIN_ID, f"📥 Yangi: `{data['c_sn']}`\n🔄 Kelish: {v_cnt}", reply_markup=kb)
    await message.answer("✅ Adminga yuborildi.", reply_markup=get_customer_menu()); await state.clear()

@dp.callback_query(F.data.startswith("adm_to_mec_"))
async def adm_to_mec(callback: types.CallbackQuery):
    sn = callback.data.split("_")[3]
    staff_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(1)
    mech = next((r['chat_id'] for r in staff_sheet.get_all_records() if str(r['phone']) == MIRKOMIL_PHONE), None)
    if mech:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Qabul", callback_data=f"m_rec_{sn}")]])
        await bot.send_message(mech, f"🔔 Yangi SN: `{sn}`", reply_markup=kb)
    await callback.message.edit_text("✅ Mexanikka yuborildi."); await callback.answer()

@dp.callback_query(F.data.startswith("m_rec_"))
async def mech_rec_start(callback: types.CallbackQuery, state: FSMContext):
    sn = callback.data.split("_")[2]; await state.update_data(m_sn=sn)
    await callback.message.answer(f"📸 `{sn}`ni tasdiqlash uchun skanerlang."); await state.set_state(ServiceState.mech_receiving_scan); await callback.answer()

@dp.message(ServiceState.mech_receiving_scan, F.photo)
async def mech_rec_finish(message: types.Message, state: FSMContext):
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: return
    sn = codes[0].data.decode('utf-8'); data = await state.get_data()
    if sn == data['m_sn']:
        battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
        row_idx = find_battery_row(sn)
        if row_idx:
            battery_sheet.update_cell(row_idx, 18, 'Skladga olindi')
            battery_sheet.update_cell(row_idx, 3, message.from_user.full_name) # Mexanik_ismi_k (3)
            await message.answer("✅ Skladga olindi.", reply_markup=get_mechanic_menu()); await state.clear()

# --- TOPSHIRISH (Bulk) ---
@dp.message(F.text == "📤 Tayyorini qabul qilish")
async def bulk_start(message: types.Message, state: FSMContext):
    await message.answer("Modelni tanlang:", reply_markup=get_model_keyboard()); await state.set_state(ServiceState.waiting_return_model)

@dp.message(ServiceState.waiting_return_model, F.text.in_(["🔋 Wind3", "🔋 Yandeks"]))
async def bulk_count(message: types.Message, state: FSMContext):
    await state.update_data(ret_mod=message.text); await message.answer(f"Nechta?", reply_markup=get_return_count_keyboard())

@dp.callback_query(F.data.startswith("ret_cnt_"))
async def bulk_adm_req(callback: types.CallbackQuery, state: FSMContext):
    cnt = callback.data.split("_")[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ruxsat", callback_data=f"adm_bulk_ok_{cnt}")]])
    await bot.send_message(ADMIN_ID, f"🎁 Mijoz {cnt} ta olmoqchi.", reply_markup=kb)
    await callback.message.edit_text("⏳ Kutilmoqda..."); await callback.answer()

@dp.callback_query(F.data.startswith("adm_bulk_ok_"))
async def adm_bulk_approve(callback: types.CallbackQuery):
    cnt = callback.data.split("_")[3]
    staff_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(1)
    mech = next((r['chat_id'] for r in staff_sheet.get_all_records() if str(r['phone']) == MIRKOMIL_PHONE), None)
    if mech:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"m_bulk_{cnt}")]])
        await bot.send_message(mech, f"🎁 {cnt} ta chiqaring.", reply_markup=kb)
    await callback.message.edit_text("✅ Tasdiqlandi."); await callback.answer()

@dp.callback_query(F.data.startswith("m_bulk_"))
async def m_bulk_scan(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2]); await state.update_data(b_t=cnt, b_s=0)
    await callback.message.answer(f"1/{cnt} - Skanerlang:"); await state.set_state(ServiceState.mech_bulk_scanning); await callback.answer()

@dp.message(ServiceState.mech_bulk_scanning, F.photo)
async def m_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data(); target, scanned = data['b_t'], data['b_s']
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: return
    sn = codes[0].data.decode('utf-8')
    
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        curr_status = battery_sheet.cell(row_idx, 18).value
        if curr_status == 'Tayyor':
            battery_sheet.update_cell(row_idx, 18, 'Yuborilmoqda')
            battery_sheet.update_cell(row_idx, 10, message.from_user.full_name) # Mexanik_ismi_ch (10)
            battery_sheet.update_cell(row_idx, 13, sn) # Seriya_tasdigi (13)
            scanned += 1; await state.update_data(b_s=scanned)
            if scanned < target: await message.answer(f"✅ {scanned}/{target} skanerlandi. Keyingisi:")
            else:
                staff_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(1)
                cust = next((r['chat_id'] for r in staff_sheet.get_all_records() if str(r['phone']) == MY_PHONE), None)
                if cust: await bot.send_message(cust, "🎁 Qabul qiling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"c_bulk_{target}")]]))
                await message.answer("✅ Hammasi skanerlandi."); await state.clear()
        else: await message.answer("❌ Bu SN tayyor emas!")

@dp.callback_query(F.data.startswith("c_bulk_"))
async def c_bulk_init(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2]); await state.update_data(c_t=cnt, c_s=0)
    await callback.message.answer(f"1/{cnt} - Skanerlang:"); await state.set_state(ServiceState.cust_bulk_scanning); await callback.answer()

@dp.message(ServiceState.cust_bulk_scanning, F.photo)
async def c_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data(); target, scanned = data['c_t'], data['c_s']
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: return
    sn = codes[0].data.decode('utf-8')
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    row_idx = find_battery_row(sn)
    if row_idx:
        battery_sheet.update_cell(row_idx, 18, 'Topshirildi')
        battery_sheet.update_cell(row_idx, 11, message.from_user.full_name) # Mijoz_ismi_ch (11)
        battery_sheet.update_cell(row_idx, 12, get_now()) # Topshirilgan_vaqt (12)
    scanned += 1; await state.update_data(c_s=scanned)
    if scanned < target: await message.answer(f"✅ {scanned}/{target} qabul qilindi.")
    else: await message.answer("🏁 Tamom!", reply_markup=get_customer_menu()); await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    battery_sheet = CLIENT.open_by_key(SHEET_ID).get_worksheet(0)
    records = battery_sheet.get_all_records()
    stats = {}
    for r in records:
        s = r.get('Holati', 'Noma’lum')
        stats[s] = stats.get(s, 0) + 1
    res = "📊 Statistika:\n" + "\n".join([f"- {s}: {c}" for s, c in stats.items()])
    await message.answer(res)

if __name__ == '__main__':
    print("Bot ishga tushdi...")
    asyncio.run(dp.start_polling(bot))
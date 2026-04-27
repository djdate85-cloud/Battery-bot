import sqlite3
import asyncio
import cv2
import numpy as np
from datetime import datetime
from pyzbar.pyzbar import decode
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

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- BAZANI TAYYORLASH ---
def init_db():
    conn = sqlite3.connect('service_bot.db')
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS batteries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Mijoz_ismi_kirish TEXT, 
        Mexanik_ismi_kirish TEXT,
        Seriya_raqami TEXT UNIQUE, 
        Qabul_qilingan_vaqt DATETIME,
        Muammo TEXT, 
        Adminga_yuborilgan_vaqt DATETIME,
        Skladga_olingan_vaqt DATETIME, 
        Skladdan_chiqarilgan_vaqt DATETIME,
        Mexanik_ismi_chiqish TEXT, 
        Mijoz_ismi_chiqish TEXT,
        Topshirilgan_vaqt DATETIME, 
        Seriya_tasdigi TEXT,
        Remont_soni INTEGER DEFAULT 0, 
        Tarix_eslatmalari TEXT,
        Qaytarish_muddati TEXT, 
        Model TEXT, 
        Holati TEXT,
        Tashrif_soni INTEGER DEFAULT 0
    )""")
    cursor.execute("CREATE TABLE IF NOT EXISTS staff (phone TEXT PRIMARY KEY, chat_id INTEGER, role TEXT, full_name TEXT)")
    conn.commit()
    conn.close()

init_db()

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

# --- TUGMALAR ---
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
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT role FROM staff WHERE chat_id = ?", (message.from_user.id,))
    res = cursor.fetchone(); conn.close()
    if res:
        menu = get_customer_menu() if res[0] == 'customer' else get_mechanic_menu()
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
        conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO staff (phone, chat_id, role, full_name) VALUES (?, ?, ?, ?)", (phone, message.from_user.id, role, message.from_user.full_name))
        conn.commit(); conn.close()
        menu = get_customer_menu() if role == 'customer' else get_mechanic_menu()
        await message.answer(f"Muvaffaqiyatli kirdingiz!", reply_markup=menu)
        await state.clear()
    else:
        await message.answer("Ruxsat berilmadi. ❌")

# --- QABUL QILISH MANTIQI ---
async def save_or_update_battery(sn, model, problem, customer, status):
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT Topshirilgan_vaqt, Tashrif_soni FROM batteries WHERE Seriya_raqami = ?", (sn,))
    eski = cursor.fetchone()
    
    now_str = get_now()
    duration = "Birinchi marta"
    v_count = 1

    if eski:
        v_count = (eski[1] or 0) + 1
        if eski[0]:
            d1 = datetime.strptime(eski[0], "%Y-%m-%d %H:%M:%S")
            d2 = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
            diff = d2 - d1
            duration = f"{diff.days} kun"

    cursor.execute("""INSERT INTO batteries (Seriya_raqami, Model, Muammo, Mijoz_ismi_kirish, Qabul_qilingan_vaqt, Holati, Qaytarish_muddati, Tashrif_soni)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                      ON CONFLICT(Seriya_raqami) DO UPDATE SET
                      Model=excluded.Model, Muammo=excluded.Muammo, Mijoz_ismi_kirish=excluded.Mijoz_ismi_kirish,
                      Qabul_qilingan_vaqt=excluded.Qabul_qilingan_vaqt, Holati=excluded.Holati, Qaytarish_muddati=excluded.Qaytarish_muddati,
                      Tashrif_soni=excluded.Tashrif_soni""", 
                   (sn, model, problem, customer, now_str, status, duration, v_count))
    conn.commit(); conn.close()
    return v_count, duration

# --- MEXANIK: TO'G'RIDAN-TO'G'RI QABUL ---
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
    data = await state.get_data()
    v_cnt, dur = await save_or_update_battery(data['m_dir_sn'], data['m_dir_model'], message.text, "Direct Scan", "Skladga olindi")
    
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("UPDATE batteries SET Mexanik_ismi_kirish = ? WHERE Seriya_raqami = ?", (message.from_user.full_name, data['m_dir_sn']))
    conn.commit(); conn.close()

    await message.answer(f"✅ Skladga olindi.\n🔄 Kelish: {v_cnt}\n⏱ Muddat: {dur}", reply_markup=get_mechanic_menu())
    await state.clear()

# --- ISHLAR RO'YXATI ---
@dp.message(F.text == "🛠 Ishlar ro'yxati")
async def mech_work_list(message: types.Message):
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT Seriya_raqami, Model, Muammo FROM batteries WHERE Holati = 'Skladga olindi'")
    jobs = cursor.fetchall(); conn.close()
    if not jobs: await message.answer("Hozircha ish yo'q."); return
    for sn, model, prob in jobs:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛠 Remontga yuborish", callback_data=f"m_rep_{sn}")]])
        await message.answer(f"🔋 {model}\nSN: `{sn}`\nXato: {prob}", reply_markup=kb)

@dp.callback_query(F.data.startswith("m_rep_"))
async def m_rep_to_adm(callback: types.CallbackQuery):
    sn = callback.data.replace("m_rep_", "")
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("UPDATE batteries SET Holati = 'Remontda', Adminga_yuborilgan_vaqt = ? WHERE Seriya_raqami = ?", (get_now(), sn))
    cursor.execute("SELECT Model, Muammo FROM batteries WHERE Seriya_raqami = ?", (sn,))
    res = cursor.fetchone(); conn.commit(); conn.close()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Remont bo'ldi", callback_data=f"a_ok_{sn}")],
        [InlineKeyboardButton(text="❌ Remont bo'lmadi", callback_data=f"a_no_{sn}")]
    ])
    await bot.send_message(ADMIN_ID, f"🛠 **Remont so'rovi!**\n🆔 SN: `{sn}`\n⚠️ Xato: {res[1]}", reply_markup=kb)
    await callback.message.edit_text(f"✅ `{sn}` Adminga yuborildi."); await callback.answer()

# --- ADMIN QARORI ---
@dp.callback_query(F.data.startswith("a_ok_"))
async def adm_rep_ok(callback: types.CallbackQuery):
    sn = callback.data.replace("a_ok_", "")
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("UPDATE batteries SET Holati = 'Tayyor', Skladga_olingan_vaqt = ?, Remont_soni = Remont_soni + 1 WHERE Seriya_raqami = ?", (get_now(), sn))
    conn.commit(); conn.close()
    await callback.message.edit_text(f"✅ `{sn}` Tayyor skladga o'tdi."); await callback.answer()

@dp.callback_query(F.data.startswith("a_no_"))
async def adm_rep_no(callback: types.CallbackQuery):
    sn = callback.data.replace("a_no_", "")
    await callback.message.edit_text(f"❌ Rad etish sababi:", reply_markup=get_fail_reasons_kb(sn)); await callback.answer()

@dp.callback_query(F.data.startswith("f_r_"))
async def save_fail_reason(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.replace("f_r_", "").split("_", 1)
    sn, reason = data[0], data[1]
    if reason == "Boshqa":
        await state.update_data(fail_sn=sn); await callback.message.answer("Sababni yozing:"); await state.set_state(ServiceState.waiting_fail_reason)
    else:
        conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
        cursor.execute("UPDATE batteries SET Holati = 'Brak', Skladdan_chiqarilgan_vaqt = ?, Tarix_eslatmalari = ? WHERE Seriya_raqami = ?", (get_now(), reason, sn))
        conn.commit(); conn.close(); await callback.message.edit_text(f"🗑 `{sn}` brak qilindi."); await callback.answer()

# --- MIJOZ TOPSHIRISH ---
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
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM staff WHERE phone = ?", (MIRKOMIL_PHONE,))
    mech = cursor.fetchone(); conn.close()
    if mech:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Qabul", callback_data=f"m_rec_{sn}")]])
        await bot.send_message(mech[0], f"🔔 Yangi SN: `{sn}`", reply_markup=kb)
    await callback.message.edit_text("✅ Mexanikka yuborildi."); await callback.answer()

@dp.callback_query(F.data.startswith("m_rec_"))
async def mech_rec_start(callback: types.CallbackQuery, state: FSMContext):
    sn = callback.data.split("_")[2]
    await state.update_data(m_sn=sn)
    await callback.message.answer(f"📸 `{sn}`ni tasdiqlash uchun skanerlang."); await state.set_state(ServiceState.mech_receiving_scan); await callback.answer()

@dp.message(ServiceState.mech_receiving_scan, F.photo)
async def mech_rec_finish(message: types.Message, state: FSMContext):
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: return
    sn = codes[0].data.decode('utf-8'); data = await state.get_data()
    if sn == data['m_sn']:
        conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
        cursor.execute("UPDATE batteries SET Holati = 'Skladga olindi', Mexanik_ismi_kirish = ? WHERE Seriya_raqami = ?", (message.from_user.full_name, sn))
        conn.commit(); conn.close()
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
    cnt = callback.data.split("_")[2]; data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ruxsat", callback_data=f"adm_bulk_ok_{cnt}")]])
    await bot.send_message(ADMIN_ID, f"🎁 Mijoz {cnt} ta olmoqchi.", reply_markup=kb)
    await callback.message.edit_text("⏳ Kutilmoqda..."); await callback.answer()

@dp.callback_query(F.data.startswith("adm_bulk_ok_"))
async def adm_bulk_approve(callback: types.CallbackQuery):
    cnt = callback.data.split("_")[3]; conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM staff WHERE phone = ?", (MIRKOMIL_PHONE,))
    res = cursor.fetchone(); conn.close()
    if res:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"m_bulk_{cnt}")]])
        await bot.send_message(res[0], f"🎁 {cnt} ta chiqaring.", reply_markup=kb)
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
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("UPDATE batteries SET Holati = 'Yuborilmoqda', Mexanik_ismi_chiqish = ?, Seriya_tasdigi = ? WHERE Seriya_raqami = ? AND Holati = 'Tayyor'", (message.from_user.full_name, sn, sn))
    if cursor.rowcount > 0:
        scanned += 1; await state.update_data(b_s=scanned)
        if scanned < target: await message.answer(f"✅ {scanned}/{target} skanerlandi. Keyingisi:")
        else:
            cursor.execute("SELECT chat_id FROM staff WHERE phone = ?", (MY_PHONE,))
            cust = cursor.fetchone()
            if cust: await bot.send_message(cust[0], "🎁 Qabul qiling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Skaner", callback_data=f"c_bulk_{target}")]]))
            await message.answer("✅ Hammasi skanerlandi."); await state.clear()
    else: await message.answer("❌ Bu SN tayyor emas!")
    conn.commit(); conn.close()

@dp.callback_query(F.data.startswith("c_bulk_"))
async def c_bulk_init(callback: types.CallbackQuery, state: FSMContext):
    cnt = int(callback.data.split("_")[2]); await state.update_data(c_t=cnt, c_s=0, c_l=[])
    await callback.message.answer(f"1/{cnt} - Skanerlang:"); await state.set_state(ServiceState.cust_bulk_scanning); await callback.answer()

@dp.message(ServiceState.cust_bulk_scanning, F.photo)
async def c_bulk_proc(message: types.Message, state: FSMContext):
    data = await state.get_data(); target, scanned, clist = data['c_t'], data['c_s'], data['c_l']
    photo = message.photo[-1]; file = await bot.get_file(photo.file_id); file_bytes = await bot.download_file(file.file_path)
    nparr = np.frombuffer(file_bytes.read(), np.uint8); img = cv2.imdecode(nparr, cv2.IMREAD_COLOR); codes = decode(img)
    if not codes: return
    sn = codes[0].data.decode('utf-8')
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("UPDATE batteries SET Holati = 'Topshirildi', Mijoz_ismi_chiqish = ?, Topshirilgan_vaqt = ? WHERE Seriya_raqami = ?", (message.from_user.full_name, get_now(), sn))
    conn.commit(); conn.close()
    scanned += 1; await state.update_data(c_s=scanned)
    if scanned < target: await message.answer(f"✅ {scanned}/{target} qabul qilindi.")
    else: await message.answer("🏁 Tamom!", reply_markup=get_customer_menu()); await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('service_bot.db'); cursor = conn.cursor()
    cursor.execute("SELECT Holati, COUNT(*) FROM batteries GROUP BY Holati")
    stats = cursor.fetchall(); conn.close()
    res = "📊 Statistika:\n"
    for s, c in stats: res += f"- {s}: {c}\n"
    await message.answer(res)

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
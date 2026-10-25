import asyncio
import logging
import sqlite3
import datetime
import re
import os
import aiohttp
from dotenv import load_dotenv
import time
import phonenumbers

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

# ==========================================
# কনফিগারেশন (Railway Environment Variables)
# ==========================================
load_dotenv()

# Railway-তে Variables সেট করলেই এটি কাজ করবে
BOT_TOKEN = "8895921858:AAHL_YTzOoD-6aDE7f0PzjYSTFRxdUf_Cz4"
ADMIN_ID = 6820798198  # আপনার আইডি
LAMIX_TOKEN = "PDRCif2kg-Bdrlo1rWVouEeiEliVVb2HP_SBfOnHX10"
LAMIX_BASE_URL = "https://panel.lamix.org/api/v1"
FORCE_JOIN_CHANNEL = "" 

logging.basicConfig(level=logging.INFO)

# ==========================================
# ডাটাবেস ডিজাইন
# ==========================================
def init_db():
    conn = sqlite3.connect("sky_sms.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, last_order_time REAL DEFAULT 0.0)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, 
        service_category TEXT, country_name TEXT, country_flag TEXT, 
        price REAL, status TEXT DEFAULT 'AVAILABLE')""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, number_id INTEGER, 
        status TEXT DEFAULT 'PENDING', created_at TIMESTAMP, otp_code TEXT)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY, icon TEXT)")
    cursor.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT, 
        amount REAL, trx_id TEXT, status TEXT DEFAULT 'PENDING', created_at TIMESTAMP)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=None):
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cur.fetchone()
    conn.close()
    return res[0] if res else default

def set_setting(key, value):
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_stock_count():
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM numbers WHERE status = 'AVAILABLE'")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_country_info(phone_number):
    try:
        parsed_num = phonenumbers.parse("+" + phone_number, None)
        region_name = phonenumbers.region_code_for_number(parsed_num)
        country_name = phonenumbers.geocoder.description_for_number(parsed_num, "en")
        
        flag = ""
        if region_name:
            flag = chr(ord(region_name[0]) + 127397) + chr(ord(region_name[1]) + 127397)
        else:
            flag = "🌍"
            country_name = "GLOBAL"
            
        return country_name.upper() if country_name else region_name, flag
    except:
        return "GLOBAL", "🌍"

# ==========================================
# ইনিশিয়ালাইজেশন
# ==========================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

class AdminStates(StatesGroup):
    waiting_for_channel_name = State()
    waiting_for_channel_link = State()
    waiting_for_cooldown_time = State()
    waiting_for_refund_time = State() 
    waiting_for_number_limit = State()
    waiting_for_bal_user = State()
    waiting_for_bal_amount = State()
    waiting_for_txt_file = State()
    waiting_for_assign_user = State()
    waiting_for_assign_number = State()
    waiting_for_category_name = State()
    waiting_for_category_icon = State()
    waiting_for_broadcast = State()
    waiting_for_bkash_num = State()
    waiting_for_nagad_num = State()
    waiting_for_binance_id = State()
    waiting_for_min_dep = State()
    waiting_for_dollar_rate = State()
    waiting_for_new_admin_id = State()
    waiting_for_support_link = State()
    waiting_for_rate_amount = State()

class UserStates(StatesGroup):
    waiting_for_usd_amount = State()
    waiting_for_trx_id = State()
    waiting_for_screenshot = State()
    waiting_for_otp_check_number = State()
    waiting_for_top_country_category = State()

class AdminManageStates(StatesGroup):
    waiting_for_remove_id = State()

# ==========================================
# কীবোর্ড ডিজাইন
# ==========================================
def user_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>📲 𝗚𝗘𝗧 𝗡𝗨𝗠𝗕𝗘𝗥</b>", callback_data="get_service", style="success"),
         InlineKeyboardButton(text="<b>🔍 𝗖𝗛𝗘𝗖𝗞 𝗢𝗧𝗣</b>", callback_data="check_otp_menu", style="primary")],
        [InlineKeyboardButton(text="<b>💳 𝗕𝗔𝗟𝗔𝗡𝗖𝗘</b>", callback_data="balance", style="primary"),
         InlineKeyboardButton(text="<b>🌍 𝗧𝗢𝗣 𝗖𝗢𝗨𝗡𝗧𝗥𝗬</b>", callback_data="top_country", style="success")],
        [InlineKeyboardButton(text="<b>🛡️ 𝗦𝗨𝗣𝗣𝗢𝗥𝗧</b>", callback_data="support_menu", style="danger")],
        [InlineKeyboardButton(text="<b>⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟</b>", callback_data="admin_panel", style="danger")]
    ])

def support_menu_keyboard():
    support_link = get_setting("support_link", "https://t.me/telegram")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>💬 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧</b>", url=support_link, style="primary")],
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="main_menu", style="danger")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>📢 𝗦𝗘𝗧 𝗖𝗛𝗔𝗡𝗡𝗘𝗟</b>", callback_data="admin_set_channel", style="primary"),
         InlineKeyboardButton(text="<b>⏱️ 𝗦𝗘𝗧 𝗖𝗢𝗢𝗟𝗗𝗢𝗪𝗡</b>", callback_data="admin_set_cooldown", style="primary")],
        [InlineKeyboardButton(text="<b>🔄 𝗦𝗘𝗧 𝗥𝗘𝗙𝗨𝗡𝗗 𝗧𝗜𝗠𝗘</b>", callback_data="admin_set_refund_time", style="primary"),
         InlineKeyboardButton(text="<b>🔢 𝗦𝗘𝗧 𝗡𝗨𝗠 𝗟𝗜𝗠𝗜𝗧</b>", callback_data="admin_set_num_limit", style="primary")],
        [InlineKeyboardButton(text="<b>🛡️ 𝗦𝗘𝗧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧</b>", callback_data="admin_set_support", style="primary"),
         InlineKeyboardButton(text="<b>📱 𝗦𝗘𝗧 𝗕𝗞𝗔𝗦𝗛</b>", callback_data="admin_set_bkash", style="success")],
        [InlineKeyboardButton(text="<b>💵 𝗦𝗘𝗧 𝗡𝗔𝗚𝗔𝗗</b>", callback_data="admin_set_nagad", style="success"),
         InlineKeyboardButton(text="<b>🪙 𝗦𝗘𝗧 𝗕𝗜𝗡𝗔𝗡𝗖𝗘</b>", callback_data="admin_set_binance", style="success")],
        [InlineKeyboardButton(text="<b>💳 𝗦𝗘𝗧 𝗠𝗜𝗡 𝗗𝗘𝗣</b>", callback_data="admin_set_min_dep", style="primary"),
         InlineKeyboardButton(text="<b>💱 𝗦𝗘𝗧 𝗚𝗟𝗢𝗕𝗔𝗟 𝗥𝗔𝗧𝗘</b>", callback_data="admin_set_rate", style="primary")],
        [InlineKeyboardButton(text="<b>💰 𝗠𝗔𝗡𝗔𝗚𝗘 𝗕𝗔𝗟</b>", callback_data="admin_manage_balance", style="success"),
         InlineKeyboardButton(text="<b>👥 𝗨𝗦𝗘𝗥𝗦 𝗟𝗜𝗦𝗧</b>", callback_data="admin_users_list", style="primary")],
        [InlineKeyboardButton(text="<b>📥 𝗨𝗣𝗟𝗢𝗔𝗗 𝗡𝗨𝗠</b>", callback_data="admin_upload_start", style="success"),
         InlineKeyboardButton(text="<b>💲 𝗦𝗘𝗧 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 𝗥𝗔𝗧𝗘</b>", callback_data="admin_set_country_rate", style="primary")],
        [InlineKeyboardButton(text="<b>🗑️ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗡𝗨𝗠𝗕𝗘𝗥𝗦</b>", callback_data="admin_remove_numbers", style="danger"),
         InlineKeyboardButton(text="<b>➕ 𝗔𝗗𝗗 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬</b>", callback_data="admin_add_category", style="primary")],
        [InlineKeyboardButton(text="<b>🎯 𝗔𝗦𝗦𝗜𝗚𝗡 𝗡𝗨𝗠</b>", callback_data="admin_assign_number", style="primary"),
         InlineKeyboardButton(text="<b>📣 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧</b>", callback_data="admin_broadcast", style="danger")],
        [InlineKeyboardButton(text="<b>👑 𝗔𝗗𝗠𝗜𝗡𝗦</b>", callback_data="admin_manage_admins", style="danger")],
        [InlineKeyboardButton(text="<b>🔙 𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨</b>", callback_data="main_menu", style="danger")]
    ])

def back_to_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗔𝗗𝗠𝗜𝗡</b>", callback_data="admin_panel", style="danger")]
    ])

def category_selection_menu(action_prefix):
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT name, icon FROM categories")
    rows = cur.fetchall()
    conn.close()
    kb = []
    if not rows:
        kb.append([InlineKeyboardButton(text="<b>🟢 𝗪𝗛𝗔𝗧𝗦𝗔𝗣𝗣</b>", callback_data=f"{action_prefix}_WHATSAPP", style="success")])
    else:
        for row in rows:
            kb.append([InlineKeyboardButton(text=f"<b>{row[1]} {row[0].upper()}</b>", callback_data=f"{action_prefix}_{row[0]}", style="success")])
    kb.append([InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="admin_panel" if action_prefix == "upload_cat" else "main_menu", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def country_selection_menu(countries, service):
    kb = []
    for c in countries:
        btn_text = f"<b>{c['flag']} {c['country']}</b>"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy_num_{service}_{c['country']}", style="success")])
    kb.append([InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="get_service", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_number_keyboard(numbers_list, service):
    kb = []
    for num in numbers_list:
        btn_text = f"{num['country_flag']} 📋 +{num['number']}"
        kb.append([InlineKeyboardButton(text=f"<b>{btn_text}</b>", copy_text=types.CopyTextButton(text=num['number']), style="success")])
    kb.append([InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data=f"view_cat_{service}", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def order_menu(order_id, price, service):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"<b>🔄 𝗖𝗛𝗔𝗡𝗚𝗘 𝗡𝗨𝗠𝗕𝗘𝗥 (${price:.4f})</b>", callback_data=f"change_number_{order_id}", style="primary"),
         InlineKeyboardButton(text="<b>🌍 𝗖𝗛𝗔𝗡𝗚𝗘 𝗖𝗢𝗨𝗡𝗧𝗥𝗬</b>", callback_data=f"change_country_{order_id}_{service}", style="success")],
        [InlineKeyboardButton(text="<b>💸 𝗥𝗘𝗙𝗨𝗡𝗗</b>", callback_data=f"refund_{order_id}", style="danger"),
         InlineKeyboardButton(text="<b>❌ 𝗖𝗟𝗢𝗦𝗘</b>", callback_data=f"close_{order_id}", style="danger")]
    ])

def force_join_keyboard():
    channel_name = get_setting("force_join_name", "OUR CHANNEL")
    channel_link = get_setting("force_join_link", "")
    if not channel_link:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="<b>✅ 𝗩𝗘𝗥𝗜𝗙𝗬</b>", callback_data="verify_join", style="success")]])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"<b>📢 𝗝𝗢𝗜𝗡 {channel_name}</b>", url=channel_link, style="primary")],
        [InlineKeyboardButton(text="<b>✅ 𝗩𝗘𝗥𝗜𝗙𝗬</b>", callback_data="verify_join", style="success")]
    ])

def deposit_methods_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>📱 𝗕𝗞𝗔𝗦𝗛</b>", callback_data="dep_bkash", style="success"),
         InlineKeyboardButton(text="<b>💵 𝗡𝗔𝗚𝗔𝗗</b>", callback_data="dep_nagad", style="success")],
        [InlineKeyboardButton(text="<b>🪙 𝗕𝗜𝗡𝗔𝗡𝗖𝗘</b>", callback_data="dep_binance", style="primary")],
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="balance", style="danger")]
    ])

def admin_deposit_approval_keyboard(deposit_id, user_id, amount):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘</b>", callback_data=f"appr_{deposit_id}_{user_id}_{amount}", style="success")],
        [InlineKeyboardButton(text="<b>❌ 𝗥𝗘𝗝𝗘𝗖𝗧</b>", callback_data=f"rej_{deposit_id}", style="danger")]
    ])

def admin_management_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>➕ 𝗔𝗗𝗗 𝗔𝗗𝗠𝗜𝗡</b>", callback_data="admin_add_new", style="success"),
         InlineKeyboardButton(text="<b>➖ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗔𝗗𝗠𝗜𝗡</b>", callback_data="admin_remove", style="danger")],
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗔𝗗𝗠𝗜𝗡</b>", callback_data="admin_panel", style="danger")]
    ])

def otp_result_keyboard(country_flag, number, otp_code, full_sms):
    otp_display = otp_code if otp_code else "N/A"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"<b>{country_flag} +{number}</b>", copy_text=types.CopyTextButton(text=number), style="primary")],
        [InlineKeyboardButton(text="<b>📄 𝗙𝗨𝗟𝗟</b>", copy_text=types.CopyTextButton(text=full_sms), style="success"),
         InlineKeyboardButton(text=f"<b>🔑 𝗢𝗧𝗣: {otp_display}</b>", copy_text=types.CopyTextButton(text=otp_code if otp_code else full_sms), style="success")]
    ])

# ==========================================
# হেল্পার ফাংশন
# ==========================================
def check_cooldown(user_id):
    cooldown_seconds = float(get_setting("cooldown_seconds", 60))
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT last_order_time FROM users WHERE user_id=?", (user_id,))
    last_time = cur.fetchone()[0]
    conn.close()
    time_passed = time.time() - last_time
    if time_passed < cooldown_seconds:
        return False, int(cooldown_seconds - time_passed)
    return True, 0

def update_cooldown(user_id):
    conn = sqlite3.connect("sky_sms.db")
    conn.execute("UPDATE users SET last_order_time=? WHERE user_id=?", (time.time(), user_id))
    conn.commit()
    conn.close()

async def is_user_joined(user_id):
    channel_link = get_setting("force_join_link", "")
    if not channel_link or "your_channel" in channel_link: return True
    
    try:
        chat_id = channel_link.replace("https://t.me/", "@").replace("http://t.me/", "@")
        if not chat_id.startswith("@"):
            chat_id = "@" + chat_id
            
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"Join check error: {e}")
        return True

def is_admin(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return True if res else False

# ==========================================
# ইউজার মেনু ও ডিপোজিট সিস্টেম
# ==========================================
@router.message(CommandStart())
async def start_cmd(message: Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("sky_sms.db")
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    if not await is_user_joined(user_id):
        await message.answer("⚠️ <b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗧𝗢 𝗨𝗦𝗘 𝗦𝗞𝗬 𝗦𝗠𝗦!</b>", reply_markup=force_join_keyboard())
        return

    await message.answer(f"👋 <b>𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗦𝗞𝗬 𝗦𝗠𝗦, {message.from_user.first_name.upper()}!</b>\n\n<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗡 𝗢𝗣𝗧𝗜𝗢𝗡 𝗕𝗘𝗟𝗢𝗪:</b>", reply_markup=user_main_menu())

@router.callback_query(F.data == "verify_join")
async def verify_join(callback: CallbackQuery):
    if await is_user_joined(callback.from_user.id):
        await callback.message.edit_text("<b>✅ 𝗩𝗘𝗥𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟!</b>", reply_markup=user_main_menu())
    else:
        await callback.answer("❌ 𝗬𝗢𝗨 𝗛𝗔𝗩𝗘 𝗡𝗢𝗧 𝗝𝗢𝗜𝗡𝗘𝗗 𝗬𝗘𝗧!", show_alert=True)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗡 𝗢𝗣𝗧𝗜𝗢𝗡 𝗕𝗘𝗟𝗢𝗪:</b>", reply_markup=user_main_menu())

@router.callback_query(F.data == "balance")
async def show_user_balance(callback: CallbackQuery):
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (callback.from_user.id,))
    bal = cur.fetchone()[0]
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>💳 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗡𝗢𝗪</b>", callback_data="deposit_menu", style="success")],
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="main_menu", style="danger")]
    ])
    await callback.message.edit_text(f"💰 <b>𝗬𝗢𝗨𝗥 𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${bal:.4f}</b>", reply_markup=kb)

@router.callback_query(F.data == "support_menu")
async def support_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>🛡️ 𝗡𝗘𝗘𝗗 𝗛𝗘𝗟𝗣?</b>\n\n"
        "<b>𝗖𝗟𝗜𝗖𝗞 𝗧𝗛𝗘 𝗕𝗨𝗧𝗧𝗢𝗡 𝗕𝗘𝗟𝗢𝗪 𝗧𝗢 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗢𝗨𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗧𝗘𝗔𝗠 𝗗𝗜𝗥𝗘𝗖𝗧𝗟𝗬 𝗢𝗡 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠.</b>",
        reply_markup=support_menu_keyboard()
    )

@router.callback_query(F.data == "top_country")
async def ask_top_country(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_top_country_category)
    await callback.message.edit_text("<b>🌍 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗧𝗛𝗘 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 𝗡𝗔𝗠𝗘 (e.g., WHATSAPP):</b>")

@router.message(UserStates.waiting_for_top_country_category)
async def process_top_country(message: Message, state: FSMContext):
    category = message.text.strip().upper()
    await message.answer(f"⏳ <b>𝗦𝗘𝗔𝗥𝗖𝗛𝗜𝗡𝗚 𝗧𝗢𝗣 𝗖𝗢𝗨𝗡𝗧𝗥𝗜𝗘𝗦 𝗙𝗢𝗥 {category}...</b>")
    
    headers = {"Authorization": f"Bearer {LAMIX_TOKEN}"}
    url = f"{LAMIX_BASE_URL}/messages?cli={category}&limit=100" 
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                if res.status == 200:
                    data = await res.json()
                    countries = set()
                    for record in data.get("records", []):
                        range_name = record.get("range", "UNKNOWN")
                        country = range_name.split(" ")[0].upper() 
                        countries.add(country)
                    
                    if not countries:
                        await state.clear()
                        return await message.answer(f"❌ <b>𝗡𝗢 𝗔𝗖𝗧𝗜𝗩𝗘 𝗖𝗢𝗨𝗡𝗧𝗥𝗜𝗘𝗦 𝗙𝗢𝗨𝗡𝗗 𝗙𝗢𝗥 {category} 𝗥𝗜𝗚𝗛𝗧 𝗡𝗢𝗪.</b>", reply_markup=user_main_menu())

                    text = f"🌍 <b>𝗔𝗖𝗧𝗜𝗩𝗘 𝗖𝗢𝗨𝗡𝗧𝗥𝗜𝗘𝗦 𝗙𝗢𝗥 {category}:</b>\n\n"
                    for idx, country in enumerate(list(countries)[:10], 1):
                        text += f"<b>{idx}. {country}</b>\n"
                    
                    await state.clear()
                    await message.answer(text, reply_markup=user_main_menu())
                else:
                    await state.clear()
                    await message.answer("❌ <b>𝗙𝗔𝗜𝗟𝗘𝗗 𝗧𝗢 𝗙𝗘𝗧𝗖𝗛 𝗗𝗔𝗧𝗔 𝗙𝗥𝗢𝗠 𝗣𝗔𝗡𝗘𝗟.</b>", reply_markup=user_main_menu())
    except:
        await state.clear()
        await message.answer("❌ <b>𝗡𝗘𝗧𝗪𝗢𝗥𝗞 𝗘𝗥𝗥𝗢𝗥. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗧𝗥𝗬 𝗟𝗔𝗧𝗘𝗥.</b>", reply_markup=user_main_menu())

@router.callback_query(F.data == "check_otp_menu")
async def ask_otp_check_number(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_otp_check_number)
    await callback.message.edit_text("<b>🔍 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗧𝗛𝗘 𝗡𝗨𝗠𝗕𝗘𝗥 𝗧𝗢 𝗖𝗛𝗘𝗖𝗞 𝗢𝗧𝗣 (e.g., 84325865649):</b>")

@router.message(UserStates.waiting_for_otp_check_number)
async def process_otp_check(message: Message, state: FSMContext):
    number = message.text.strip().replace("+", "")
    await message.answer("⏳ <b>𝗦𝗘𝗔𝗥𝗖𝗛𝗜𝗡𝗚 𝗙𝗢𝗥 𝗢𝗧𝗣 𝗜𝗡 𝗣𝗔𝗡𝗘𝗟...</b>")
    
    headers = {"Authorization": f"Bearer {LAMIX_TOKEN}"}
    params = {"number": number, "limit": 10}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{LAMIX_BASE_URL}/messages", headers=headers, params=params) as res:
            if res.status == 200:
                data = await res.json()
                if data.get("records"):
                    latest_record = data["records"][0]
                    content = latest_record["content"]
                    
                    flag, _ = get_country_info(number)
                    
                    match = re.search(r'\d{4,6}', content)
                    otp_code = match.group(0) if match else None
                    
                    text = (
                        f"<b>✅ 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗙𝗢𝗨𝗡𝗗!</b>\n\n"
                        f"<b>👇 𝗖𝗟𝗜𝗖𝗞 𝗢𝗡 𝗧𝗛𝗘 𝗕𝗨𝗧𝗧𝗢𝗡 𝗧𝗢 𝗖𝗢𝗣𝗬 𝗜𝗧:</b>\n"
                    )
                    
                    await message.answer(
                        text, 
                        reply_markup=otp_result_keyboard(flag, number, otp_code, content)
                    )
                    await state.clear()
                    return
    await message.answer("❌ <b>𝗡𝗢 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗙𝗢𝗨𝗡𝗗 𝗙𝗢𝗥 𝗧𝗛𝗜𝗦 𝗡𝗨𝗠𝗕𝗘𝗥 𝗜𝗡 𝗧𝗛𝗘 𝗟𝗔𝗦𝗧 𝟮𝟰 𝗛𝗢𝗨𝗥𝗦.</b>", reply_markup=user_main_menu())
    await state.clear()

# ডিপোজিট
@router.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text("<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗠𝗘𝗧𝗛𝗢𝗗:</b>", reply_markup=deposit_methods_keyboard())

@router.callback_query(F.data.startswith("dep_"))
async def process_deposit_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1].upper()
    min_dep = float(get_setting("min_deposit", "1.00"))
    dollar_rate = float(get_setting("dollar_rate", "130.0"))
    
    if method == "BKASH":
        num = get_setting("bkash_number", "NOT SET")
        copy_btn = InlineKeyboardButton(text="<b>📋 𝗖𝗢𝗣𝗬 𝗕𝗞𝗔𝗦𝗛 𝗡𝗨𝗠𝗕𝗘𝗥</b>", copy_text=types.CopyTextButton(text=num), style="primary")
        display_text = f"📱 <b>𝗕𝗞𝗔𝗦𝗛 𝗗𝗘𝗣𝗢𝗦𝗜𝗧</b>\n\n<b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗠𝗢𝗡𝗘𝗬 𝗧𝗢 𝗧𝗛𝗜𝗦 𝗡𝗨𝗠𝗕𝗘𝗥:</b>\n<code>{num}</code>\n\n<b>𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧: ${min_dep}</b>\n<b>𝟭 𝗨𝗦𝗗 = {dollar_rate} 𝗕𝗗𝗧</b>\n\n<b>𝗛𝗢𝗪 𝗠𝗔𝗡𝗬 𝗨𝗦𝗗 𝗗𝗢 𝗬𝗢𝗨 𝗪𝗔𝗡𝗧 𝗧𝗢 𝗗𝗘𝗣𝗢𝗦𝗜𝗧?</b>"
    elif method == "NAGAD":
        num = get_setting("nagad_number", "NOT SET")
        copy_btn = InlineKeyboardButton(text="<b>📋 𝗖𝗢𝗣𝗬 𝗡𝗔𝗚𝗔𝗗 𝗡𝗨𝗠𝗕𝗘𝗥</b>", copy_text=types.CopyTextButton(text=num), style="primary")
        display_text = f"💵 <b>𝗡𝗔𝗚𝗔𝗗 𝗗𝗘𝗣𝗢𝗦𝗜𝗧</b>\n\n<b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗠𝗢𝗡𝗘𝗬 𝗧𝗢 𝗧𝗛𝗜𝗦 𝗡𝗨𝗠𝗕𝗘𝗥:</b>\n<code>{num}</code>\n\n<b>𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧: ${min_dep}</b>\n<b>𝟭 𝗨𝗦𝗗 = {dollar_rate} 𝗕𝗗𝗧</b>\n\n<b>𝗛𝗢𝗪 𝗠𝗔𝗡𝗬 𝗨𝗦𝗗 𝗗𝗢 𝗬𝗢𝗨 𝗪𝗔𝗡𝗧 𝗧𝗢 𝗗𝗘𝗣𝗢𝗦𝗜𝗧?</b>"
    elif method == "BINANCE":
        num = get_setting("binance_id", "NOT SET")
        copy_btn = InlineKeyboardButton(text="<b>📋 𝗖𝗢𝗣𝗬 𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗜𝗗</b>", copy_text=types.CopyTextButton(text=num), style="primary")
        display_text = f"🪙 <b>𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗣𝗔𝗬 𝗗𝗘𝗣𝗢𝗦𝗜𝗧</b>\n\n<b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗠𝗢𝗡𝗘𝗬 𝗧𝗢 𝗧𝗛𝗜𝗦 𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗜𝗗:</b>\n<code>{num}</code>\n\n<b>𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧: ${min_dep}</b>\n\n<b>𝗛𝗢𝗪 𝗠𝗔𝗡𝗬 𝗨𝗦𝗗 𝗗𝗢 𝗬𝗢𝗨 𝗪𝗔𝗡𝗧 𝗧𝗢 𝗗𝗘𝗣𝗢𝗦𝗜𝗧?</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [copy_btn],
        [InlineKeyboardButton(text="<b>🔙 𝗕𝗔𝗖𝗞</b>", callback_data="deposit_menu", style="danger")]
    ])
    await state.update_data(method=method)
    await state.set_state(UserStates.waiting_for_usd_amount)
    await callback.message.edit_text(display_text, reply_markup=kb)

@router.message(UserStates.waiting_for_usd_amount)
async def process_usd_amount(message: Message, state: FSMContext):
    try:
        usd_amount = float(message.text)
        min_dep = float(get_setting("min_deposit", "1.0"))
        if usd_amount < min_dep:
            return await message.answer(f"❌ <b>𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗜𝗦 ${min_dep:.2f} 𝗨𝗦𝗗. 𝗧𝗥𝗬 𝗔𝗚𝗔𝗜𝗡:</b>")
            
        data = await state.get_data()
        method = data.get('method')
        dollar_rate = float(get_setting("dollar_rate", "130.0"))
        
        if method in ["BKASH", "NAGAD"]:
            bdt_amount = usd_amount * dollar_rate
            await state.update_data(usd_amount=usd_amount, bdt_amount=bdt_amount)
            await message.answer(f"💵 <b>𝗬𝗢𝗨 𝗡𝗘𝗘𝗗 𝗧𝗢 𝗦𝗘𝗡𝗗 {bdt_amount:.2f} 𝗕𝗗𝗧 𝗧𝗢 𝗧𝗛𝗘 {method} 𝗡𝗨𝗠𝗕𝗘𝗥.</b>\n\n<b>𝗔𝗙𝗧𝗘𝗥 𝗦𝗘𝗡𝗗𝗜𝗡𝗚, 𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡 𝗜𝗗 (e.g., jjdbdjjhs):</b>")
        else:
            await state.update_data(usd_amount=usd_amount, bdt_amount=0)
            await message.answer(f"🪙 <b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 {usd_amount:.2f} 𝗨𝗦𝗗𝗧 𝗧𝗢 𝗧𝗛𝗘 𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗜𝗗.</b>\n\n<b>𝗔𝗙𝗧𝗘𝗥 𝗦𝗘𝗡𝗗𝗜𝗡𝗚, 𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗢𝗥𝗗𝗘𝗥 𝗜𝗗 (e.g., 123456789):</b>")
            
        await state.set_state(UserStates.waiting_for_trx_id)
    except:
        await message.answer("❌ <b>𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗔𝗠𝗢𝗨𝗡𝗧! 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗔 𝗡𝗨𝗠𝗕𝗘𝗥.</b>")

@router.message(UserStates.waiting_for_trx_id)
async def process_trx_id(message: Message, state: FSMContext):
    await state.update_data(trx_id=message.text)
    await state.set_state(UserStates.waiting_for_screenshot)
    await message.answer("📸 <b>𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗦𝗖𝗥𝗘𝗘𝗡𝗦𝗛𝗢𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗣𝗔𝗬𝗠𝗘𝗡𝗧:</b>")

@router.message(UserStates.waiting_for_screenshot, F.photo)
async def process_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    method = data['method']
    usd_amount = data['usd_amount']
    bdt_amount = data.get('bdt_amount', 0)
    trx_id = data['trx_id']
    user_id = message.from_user.id
    screenshot_id = message.photo[-1].file_id

    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO deposits (user_id, method, amount, trx_id, status, created_at) VALUES (?, ?, ?, ?, 'PENDING', ?)",
                (user_id, method, usd_amount, trx_id, datetime.datetime.now()))
    dep_id = cur.lastrowid
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ <b>𝗬𝗢𝗨𝗥 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗥𝗘𝗤𝗨𝗘𝗦𝗧 𝗛𝗔𝗦 𝗕𝗘𝗘𝗡 𝗦𝗘𝗡𝗧 𝗧𝗢 𝗔𝗗𝗠𝗜𝗡 𝗙𝗢𝗥 𝗔𝗣𝗣𝗥𝗢𝗩𝗔𝗟. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧.</b>", reply_markup=user_main_menu())

    admin_text = (
        f"💰 <b>𝗡𝗘𝗪 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗥𝗘𝗤𝗨𝗘𝗦𝗧!</b>\n\n"
        f"<b>𝗨𝗦𝗘𝗥 𝗜𝗗:</b> <code>{user_id}</code>\n"
        f"<b>𝗠𝗘𝗧𝗛𝗢𝗗:</b> {method}\n"
        f"<b>𝗨𝗦𝗗 𝗔𝗠𝗢𝗨𝗡𝗧:</b> ${usd_amount:.2f}\n"
    )
    if method in ["BKASH", "NAGAD"]:
        admin_text += f"<b>𝗕𝗗𝗧 𝗘𝗤𝗨𝗜𝗩𝗔𝗟𝗘𝗡𝗧:</b> {bdt_amount:.2f} 𝗕𝗗𝗧\n"
    admin_text += f"<b>𝗧𝗥𝗫 𝗜𝗗:</b> <code>{trx_id}</code>"
    
    admins = [ADMIN_ID]
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins += [row[0] for row in cur.fetchall()]
    conn.close()
    
    for adm in set(admins):
        try:
            await bot.send_photo(adm, photo=screenshot_id, caption=admin_text, reply_markup=admin_deposit_approval_keyboard(dep_id, user_id, usd_amount))
        except: pass

@router.callback_query(F.data.startswith("appr_"))
async def approve_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    _, dep_id, user_id, amount = callback.data.split("_")
    amount = float(amount)
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT status FROM deposits WHERE id=?", (dep_id,))
    if cur.fetchone()[0] != 'PENDING':
        conn.close()
        return await callback.answer("❌ 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗘𝗗!", show_alert=True)
    cur.execute("UPDATE deposits SET status='APPROVED' WHERE id=?", (dep_id,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    new_bal = cur.fetchone()[0]
    conn.close()
    await callback.message.edit_caption(caption=f"✅ <b>𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗!</b>\n<b>𝗨𝗦𝗘𝗥:</b> {user_id}\n<b>𝗔𝗠𝗢𝗨𝗡𝗧:</b> ${amount:.2f}\n<b>𝗡𝗘𝗪 𝗕𝗔𝗟𝗔𝗡𝗖𝗘:</b> ${new_bal:.2f}")
    try:
        await bot.send_message(user_id, f"🎉 <b>𝗬𝗢𝗨𝗥 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗢𝗙 ${amount:.2f} 𝗛𝗔𝗦 𝗕𝗘𝗘𝗡 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗!</b>\n💰 <b>𝗡𝗘𝗪 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${new_bal:.2f}</b>")
    except: pass

@router.callback_query(F.data.startswith("rej_"))
async def reject_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    dep_id = callback.data.split("_")[1]
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount, status FROM deposits WHERE id=?", (dep_id,))
    dep = cur.fetchone()
    if dep[2] != 'PENDING':
        conn.close()
        return await callback.answer("❌ 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗘𝗗!", show_alert=True)
    cur.execute("UPDATE deposits SET status='REJECTED' WHERE id=?", (dep_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_caption(caption=f"❌ <b>𝗥𝗘𝗝𝗘𝗖𝗧𝗘𝗗!</b>\n<b>𝗨𝗦𝗘𝗥:</b> {dep[0]}\n<b>𝗔𝗠𝗢𝗨𝗡𝗧:</b> ${dep[1]:.2f}")
    try:
        await bot.send_message(dep[0], f"❌ <b>𝗬𝗢𝗨𝗥 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗥𝗘𝗤𝗨𝗘𝗦𝗧 𝗢𝗙 ${dep[1]:.2f} 𝗛𝗔𝗦 𝗕𝗘𝗘𝗡 𝗥𝗘𝗝𝗘𝗖𝗧𝗘𝗗.</b>")
    except: pass

# ==========================================
# নাম্বার কেনা, OTP চেক ও রিফান্ড
# ==========================================
@router.callback_query(F.data == "get_service")
async def show_services(callback: CallbackQuery):
    await callback.message.edit_text("<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗦𝗘𝗥𝗩𝗜𝗖𝗘 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬:</b>", reply_markup=category_selection_menu("view_cat"))

@router.callback_query(F.data.startswith("buy_num_"))
async def process_country_purchase(callback: CallbackQuery):
    parts = callback.data.split("_")
    service = parts[2]
    country = parts[3]
    
    user_id = callback.from_user.id
    can_order, remaining = check_cooldown(user_id)
    if not can_order: 
        return await callback.answer(f"⏱ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧 {remaining} 𝗦𝗘𝗖𝗢𝗡𝗗𝗦!", show_alert=True)

    num_limit = int(get_setting("number_limit", 1))
    
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT id, number, country_flag, price FROM numbers WHERE status='AVAILABLE' AND service_category=? AND country_name=? LIMIT ?", (service, country, num_limit))
    numbers_data = cur.fetchall()
    
    if not numbers_data:
        conn.close()
        return await callback.answer("❌ 𝗡𝗢 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗟𝗘𝗙𝗧 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗖𝗢𝗨𝗡𝗧𝗥𝗬!", show_alert=True)
        
    total_price = sum([row[3] for row in numbers_data])
    
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    balance = cur.fetchone()[0]
    if balance < total_price:
        conn.close()
        return await callback.answer("❌ 𝗜𝗡𝗦𝗨𝗙𝗙𝗜𝗖𝗜𝗘𝗡𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘!", show_alert=True)

    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (total_price, user_id))
    
    order_ids = []
    purchased_numbers = []
    
    for num_row in numbers_data:
        num_id, number, flag, price = num_row
        cur.execute("UPDATE numbers SET status='IN_USE' WHERE id=?", (num_id,))
        cur.execute("INSERT INTO orders (user_id, number_id, status, created_at) VALUES (?, ?, 'PENDING', ?)", (user_id, num_id, datetime.datetime.now()))
        order_ids.append(cur.lastrowid)
        purchased_numbers.append({"country_flag": flag, "number": number})
    
    conn.commit()
    conn.close()
    
    update_cooldown(user_id)

    text = f"<b>✅ 𝗡𝗨𝗠𝗕𝗘𝗥 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘𝗗!</b>\n\n<b>👇 𝗖𝗟𝗜𝗖𝗞 𝗢𝗡 𝗧𝗛𝗘 𝗡𝗨𝗠𝗕𝗘𝗥 𝗧𝗢 𝗖𝗢𝗣𝗬 𝗜𝗧:</b>\n\n⏳ <b>𝗪𝗔𝗜𝗧𝗜𝗡𝗚 𝗙𝗢𝗥 𝗢𝗧𝗣... (𝟱 𝗠𝗜𝗡 𝗧𝗜𝗠𝗘𝗥)</b>"
    
    await callback.message.edit_text(text, reply_markup=get_number_keyboard(purchased_numbers, service))
    
    for i, order_id in enumerate(order_ids):
        price = numbers_data[i][3]
        await bot.send_message(user_id, f"🛠 <b>𝗢𝗥𝗗𝗘𝗥 𝗠𝗘𝗡𝗨 𝗙𝗢𝗥 𝗡𝗨𝗠𝗕𝗘𝗥 {i+1}</b>\n\n<b>𝗬𝗢𝗨 𝗖𝗔𝗡 𝗠𝗔𝗡𝗔𝗚𝗘 𝗬𝗢𝗨𝗥 𝗢𝗥𝗗𝗘𝗥 𝗛𝗘𝗥𝗘:</b>", reply_markup=order_menu(order_id, price, service))
        asyncio.create_task(auto_refund_timer(order_id, user_id, numbers_data[i][1], price))

@router.callback_query(F.data.startswith("close_"))
async def close_order_message(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("𝗢𝗥𝗗𝗘𝗥 𝗖𝗟𝗢𝗦𝗘𝗗.")

@router.callback_query(F.data.startswith("change_number_"))
async def change_number_only(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT number_id FROM orders WHERE id=?", (order_id,))
    old_num_id = cur.fetchone()[0]
    cur.execute("SELECT service_category, country_name, price FROM numbers WHERE id=?", (old_num_id,))
    service, country, price = cur.fetchone()
    
    cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    balance = cur.fetchone()[0]
    if balance < price:
        conn.close()
        return await callback.answer("❌ 𝗜𝗡𝗦𝗨𝗙𝗙𝗜𝗖𝗜𝗘𝗡𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘 𝗧𝗢 𝗖𝗛𝗔𝗡𝗚𝗘 𝗡𝗨𝗠𝗕𝗘𝗥!", show_alert=True)
    
    cur.execute("UPDATE numbers SET status='AVAILABLE' WHERE id=?", (old_num_id,))
    cur.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
    
    cur.execute("SELECT id, number, country_flag FROM numbers WHERE status='AVAILABLE' AND service_category=? AND country_name=? LIMIT 1", (service, country))
    new_num = cur.fetchone()
    
    if not new_num:
        conn.close()
        return await callback.answer("❌ 𝗡𝗢 𝗡𝗘𝗪 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗖𝗢𝗨𝗡𝗧𝗥𝗬!", show_alert=True)
        
    new_num_id, new_number, new_flag = new_num
    
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, user_id))
    cur.execute("UPDATE numbers SET status='IN_USE' WHERE id=?", (new_num_id,))
    cur.execute("INSERT INTO orders (user_id, number_id, status, created_at) VALUES (?, ?, 'PENDING', ?)", (user_id, new_num_id, datetime.datetime.now()))
    new_order_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    await callback.answer(f"💸 ${price} DEDUCTED FOR NEW NUMBER.", show_alert=True)
    
    text = f"<b>🔄 𝗡𝗨𝗠𝗕𝗘𝗥 𝗖𝗛𝗔𝗡𝗚𝗘𝗗!</b>\n\n<b>👇 𝗖𝗟𝗜𝗖𝗞 𝗢𝗡 𝗧𝗛𝗘 𝗡𝗘𝗪 𝗡𝗨𝗠𝗕𝗘𝗥 𝗧𝗢 𝗖𝗢𝗣𝗬 𝗜𝗧:</b>\n\n⏳ <b>𝗪𝗔𝗜𝗧𝗜𝗡𝗚 𝗙𝗢𝗥 𝗢𝗧𝗣... (𝟱 𝗠𝗜𝗡 𝗧𝗜𝗠𝗘𝗥)</b>"
    
    await callback.message.edit_text(text, reply_markup=get_number_keyboard([{"country_flag": new_flag, "number": new_number}], service))
    await bot.send_message(user_id, f"🛠 <b>𝗢𝗥𝗗𝗘𝗥 𝗠𝗘𝗡𝗨</b>\n\n<b>𝗬𝗢𝗨𝗥 𝗡𝗘𝗪 𝗢𝗥𝗗𝗘𝗥 𝗠𝗘𝗡𝗨:</b>", reply_markup=order_menu(new_order_id, price, service))
    
    asyncio.create_task(auto_refund_timer(new_order_id, user_id, new_number, price))

@router.callback_query(F.data.startswith("change_country_"))
async def change_country(callback: CallbackQuery):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    service = parts[3]
    
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT number_id, user_id FROM orders WHERE id=?", (order_id,))
    row = cur.fetchone()
    if row:
        old_num_id, user_id = row[0], row[1]
        cur.execute("SELECT price, number FROM numbers WHERE id=?", (old_num_id,))
        price_row = cur.fetchone()
        if price_row:
            price, number = price_row
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (price, user_id))
            cur.execute("DELETE FROM numbers WHERE id=?", (old_num_id,))
            cur.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
            conn.commit()
            await callback.answer(f"💸 𝗥𝗘𝗙𝗨𝗡𝗗𝗘𝗗 ${price}!", show_alert=True)
    conn.close()

    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_name, country_flag FROM numbers WHERE status = 'AVAILABLE' AND service_category = ?", (service,))
    rows = cur.fetchall()
    conn.close()
    
    if not rows: 
        return await callback.message.edit_text("❌ 𝗡𝗢 𝗦𝗧𝗢𝗖𝗞 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘!", reply_markup=user_main_menu())
        
    countries = [{"country": r[0], "flag": r[1]} for r in rows]
    text = f"🌍 <b>𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗖𝗢𝗨𝗡𝗧𝗥𝗜𝗘𝗦 𝗙𝗢𝗥 {service}:</b>\n\n👇 <b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔 𝗖𝗢𝗨𝗡𝗧𝗥𝗬:</b>"
    await callback.message.edit_text(text, reply_markup=country_selection_menu(countries, service))

@router.callback_query(F.data.startswith("check_otp_"))
async def check_otp(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT o.status, n.number FROM orders o JOIN numbers n ON o.number_id = n.id WHERE o.id=?", (order_id,))
    order_data = cur.fetchone()
    if not order_data:
        conn.close()
        return await callback.answer("❌ 𝗢𝗥𝗗𝗘𝗥 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗!", show_alert=True)
    order_status, number = order_data
    if order_status == 'SUCCESS':
        conn.close()
        return await callback.answer("❌ 𝗢𝗧𝗣 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗! 𝗡𝗢 𝗥𝗘𝗙𝗨𝗡𝗗.", show_alert=True)
    await callback.answer("🔍 𝗦𝗘𝗔𝗥𝗖𝗛𝗜𝗡𝗚 𝗙𝗢𝗥 𝗢𝗧𝗣...", show_alert=False)
    headers = {"Authorization": f"Bearer {LAMIX_TOKEN}"}
    params = {"number": number, "limit": 5}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{LAMIX_BASE_URL}/messages", headers=headers, params=params) as res:
            if res.status == 200:
                data = await res.json()
                if data.get("records"):
                    content = data["records"][0]["content"]
                    match = re.search(r'\d{4,6}', content)
                    if match:
                        otp = match.group(0)
                        cur.execute("UPDATE orders SET status='SUCCESS', otp_code=? WHERE id=?", (otp, order_id))
                        cur.execute("DELETE FROM numbers WHERE number=?", (number,))
                        conn.commit()
                        conn.close()
                        text = callback.message.text.split("\n\n")[0] + f"\n\n🔑 <b>𝗬𝗢𝗨𝗥 𝗢𝗧𝗣:</b> <code>{otp}</code>\n\n✅ <b>𝗢𝗥𝗗𝗘𝗥 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗!</b>"
                        return await callback.message.edit_text(text)
    conn.close()
    await callback.answer("❌ 𝗢𝗧𝗣 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗 𝗬𝗘𝗧. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧.", show_alert=True)

@router.callback_query(F.data.startswith("refund_"))
async def manual_refund(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, number_id, status, created_at FROM orders WHERE id=?", (order_id,))
    order = cur.fetchone()
    
    if not order:
        conn.close()
        return await callback.answer("❌ 𝗢𝗥𝗗𝗘𝗥 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗!", show_alert=True)
        
    if order[2] == 'SUCCESS':
        conn.close()
        return await callback.answer("❌ 𝗡𝗢 𝗥𝗘𝗙𝗨𝗡𝗗! 𝗢𝗧𝗣 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗.", show_alert=True)
        
    if order[2] != 'PENDING':
        conn.close()
        return await callback.answer("❌ 𝗔𝗟𝗥𝗘𝗔𝗗𝗬 𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗘𝗗!", show_alert=True)
        
    refund_time = int(get_setting("refund_time", 60))
    
    if refund_time > 0:
        created_at = datetime.datetime.strptime(order[3], "%Y-%m-%d %H:%M:%S.%f")
        time_passed = (datetime.datetime.now() - created_at).total_seconds()
        
        if time_passed < refund_time:
            remaining = refund_time - int(time_passed)
            conn.close()
            return await callback.answer(f"⏱ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧 {remaining} 𝗦𝗘𝗖𝗢𝗡𝗗𝗦 𝗕𝗘𝗙𝗢𝗥𝗘 𝗥𝗘𝗙𝗨𝗡𝗗𝗜𝗡𝗚.", show_alert=True)
        
    user_id, num_id = order[0], order[1]
    cur.execute("SELECT price, number FROM numbers WHERE id=?", (num_id,))
    price, number = cur.fetchone()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (price, user_id))
    cur.execute("UPDATE orders SET status='REFUNDED' WHERE id=?", (order_id,))
    cur.execute("DELETE FROM numbers WHERE number=?", (number,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"💸 <b>𝗥𝗘𝗙𝗨𝗡𝗗𝗘𝗗 ${price}!</b>", reply_markup=user_main_menu())

async def auto_refund_timer(order_id, user_id, number, price):
    await asyncio.sleep(300)
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT status FROM orders WHERE id=?", (order_id,))
    if cur.fetchone()[0] == 'PENDING':
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (price, user_id))
        cur.execute("UPDATE orders SET status='REFUNDED' WHERE id=?", (order_id,))
        cur.execute("DELETE FROM numbers WHERE number=?", (number,))
        conn.commit()
        try:
            await bot.send_message(user_id, f"⏰ <b>𝟱 𝗠𝗜𝗡 𝗣𝗔𝗦𝗦𝗘𝗗. 𝗡𝗢 𝗢𝗧𝗣.</b>\n💸 <b>𝗥𝗘𝗙𝗨𝗡𝗗𝗘𝗗 ${price}.</b>", reply_markup=user_main_menu())
        except: pass
    conn.close()

# ==========================================
# অ্যাডমিন প্যানেল
# ==========================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ 𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗.", show_alert=True)
    await callback.message.edit_text("<b>⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟</b>\n\n<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗡 𝗔𝗖𝗧𝗜𝗢𝗡:</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("<b>⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟</b>\n\n<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗡 𝗔𝗖𝗧𝗜𝗢𝗡:</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_country_rate")
async def ask_country_rate(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_name, country_flag FROM numbers WHERE status='AVAILABLE'")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return await callback.message.edit_text("<b>❌ NO NUMBERS AVAILABLE TO SET RATE.</b>", reply_markup=back_to_admin_menu())
        
    kb = []
    for r in rows:
        kb.append([InlineKeyboardButton(text=f"<b>{r[1]} {r[0]}</b>", callback_data=f"set_rate_{r[0]}", style="primary")])
    kb.append([InlineKeyboardButton(text="<b>🔙 BACK</b>", callback_data="admin_panel", style="danger")])
    
    await callback.message.edit_text("<b>SELECT A COUNTRY TO SET ITS RATE:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("set_rate_"))
async def ask_rate_amount(callback: CallbackQuery, state: FSMContext):
    country = callback.data.split("_")[2]
    await state.update_data(target_country=country)
    await state.set_state(AdminStates.waiting_for_rate_amount)
    await callback.message.edit_text(f"<b>ENTER NEW RATE (USD) FOR {country}:</b>")

@router.message(AdminStates.waiting_for_rate_amount)
async def save_country_rate(message: Message, state: FSMContext):
    try:
        new_rate = float(message.text)
        data = await state.get_data()
        country = data['target_country']
        
        conn = sqlite3.connect("sky_sms.db")
        cur = conn.cursor()
        cur.execute("UPDATE numbers SET price=? WHERE country_name=? AND status='AVAILABLE'", (new_rate, country))
        conn.commit()
        conn.close()
        
        await state.clear()
        await message.answer(f"<b>✅ RATE FOR {country} SET TO ${new_rate:.4f}</b>", reply_markup=admin_menu())
    except:
        await message.answer("<b>❌ INVALID AMOUNT.</b>")

@router.callback_query(F.data == "admin_remove_numbers")
async def ask_remove_country(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_name, country_flag FROM numbers WHERE status='AVAILABLE'")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return await callback.message.edit_text("<b>❌ NO NUMBERS AVAILABLE TO REMOVE.</b>", reply_markup=back_to_admin_menu())
        
    kb = []
    for r in rows:
        kb.append([InlineKeyboardButton(text=f"<b>{r[1]} {r[0]}</b>", callback_data=f"remove_{r[0]}", style="danger")])
    kb.append([InlineKeyboardButton(text="<b>🔙 BACK</b>", callback_data="admin_panel", style="danger")])
    
    await callback.message.edit_text("<b>SELECT A COUNTRY TO REMOVE ALL ITS NUMBERS:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("remove_"))
async def confirm_remove_country(callback: CallbackQuery):
    country = callback.data.split("_")[1]
    
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM numbers WHERE country_name=? AND status='AVAILABLE'", (country,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    
    await callback.answer(f"🗑 REMOVED {deleted} NUMBERS FROM {country}!", show_alert=True)
    await callback.message.edit_text(f"<b>✅ SUCCESSFULLY REMOVED ALL NUMBERS FROM {country}.</b>", reply_markup=back_to_admin_menu())

@router.callback_query(F.data == "admin_set_num_limit")
async def ask_num_limit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_number_limit)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗛𝗢𝗪 𝗠𝗔𝗡𝗬 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗧𝗢 𝗚𝗜𝗩𝗘 𝗔𝗧 𝗢𝗡𝗖𝗘 (e.g., 1 or 2):</b>")

@router.message(AdminStates.waiting_for_number_limit)
async def save_num_limit(message: Message, state: FSMContext):
    if message.text.isdigit() and int(message.text) > 0:
        set_setting("number_limit", message.text)
        await state.clear()
        await message.answer(f"<b>✅ 𝗡𝗨𝗠𝗕𝗘𝗥 𝗟𝗜𝗠𝗜𝗧 𝗦𝗘𝗧 𝗧𝗢 {message.text}.</b>", reply_markup=admin_menu())
    else:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗡𝗨𝗠𝗕𝗘𝗥. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗔 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 𝗡𝗨𝗠𝗕𝗘𝗥.</b>")

@router.callback_query(F.data == "admin_set_refund_time")
async def ask_refund_time(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_refund_time)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗥𝗘𝗙𝗨𝗡𝗗 𝗧𝗜𝗠𝗘 𝗜𝗡 𝗦𝗘𝗖𝗢𝗡𝗗𝗦 (e.g., 0 for free, 60 for 1 min):</b>")

@router.message(AdminStates.waiting_for_refund_time)
async def save_refund_time(message: Message, state: FSMContext):
    if message.text.isdigit():
        set_setting("refund_time", message.text)
        await state.clear()
        await message.answer(f"<b>✅ 𝗥𝗘𝗙𝗨𝗡𝗗 𝗧𝗜𝗠𝗘 𝗦𝗘𝗧 𝗧𝗢 {message.text} 𝗦𝗘𝗖𝗢𝗡𝗗𝗦.</b>", reply_markup=admin_menu())
    else:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗧𝗜𝗠𝗘. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗢𝗡𝗟𝗬.</b>")

@router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, balance FROM users ORDER BY balance DESC")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return await callback.message.edit_text("<b>❌ 𝗡𝗢 𝗨𝗦𝗘𝗥𝗦 𝗙𝗢𝗨𝗡𝗗.</b>", reply_markup=back_to_admin_menu())
        
    text = f"👥 <b>𝗔𝗟𝗟 𝗨𝗦𝗘𝗥𝗦 𝗕𝗔𝗟𝗔𝗡𝗖𝗘 (𝗧𝗢𝗧𝗔𝗟: {len(rows)}):</b>\n\n"
    for r in rows:
        text += f"<b>𝗜𝗗: <code>{r[0]}</code> — ${r[1]:.4f}</b>\n"
        
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>(𝗧𝗥𝗨𝗡𝗖𝗔𝗧𝗘𝗗 𝗗𝗨𝗘 𝗧𝗢 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗟𝗜𝗠𝗜𝗧)</i>"
        
    await callback.message.edit_text(text, reply_markup=back_to_admin_menu())

@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = cur.fetchall()
    conn.close()
    
    text = "👑 <b>𝗠𝗔𝗡𝗔𝗚𝗘 𝗔𝗗𝗠𝗜𝗡𝗦</b>\n\n"
    text += f"<b>𝗦𝗨𝗣𝗘𝗥 𝗔𝗗𝗠𝗜𝗡 (You): <code>{ADMIN_ID}</code></b>\n\n"
    if admins:
        text += "<b>𝗢𝗧𝗛𝗘𝗥 𝗔𝗗𝗠𝗜𝗡𝗦:</b>\n"
        for a in admins:
            text += f"<code>{a[0]}</code>\n"
    else:
        text += "<i>𝗡𝗢 𝗢𝗧𝗛𝗘𝗥 𝗔𝗗𝗠𝗜𝗡𝗦 𝗔𝗗𝗗𝗘𝗗 𝗬𝗘𝗧.</i>"
        
    await callback.message.edit_text(text, reply_markup=admin_management_keyboard())

@router.callback_query(F.data == "admin_add_new")
async def ask_new_admin_id(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: 
        return await callback.answer("⛔ 𝗢𝗡𝗟𝗬 𝗦𝗨𝗣𝗘𝗥 𝗔𝗗𝗠𝗜𝗡 𝗖𝗔𝗡 𝗔𝗗𝗗 𝗡𝗘𝗪 𝗔𝗗𝗠𝗜𝗡𝗦.", show_alert=True)
    await state.set_state(AdminStates.waiting_for_new_admin_id)
    await callback.message.edit_text("<b>𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗨𝗦𝗘𝗥 𝗜𝗗 𝗧𝗢 𝗔𝗗𝗗 𝗔𝗦 𝗔𝗗𝗠𝗜𝗡:</b>")

@router.message(AdminStates.waiting_for_new_admin_id)
async def save_new_admin(message: Message, state: FSMContext):
    try:
        new_id = int(message.text.strip())
        conn = sqlite3.connect("sky_sms.db")
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
        conn.commit()
        conn.close()
        await state.clear()
        await message.answer(f"<b>✅ 𝗨𝗦𝗘𝗥 {new_id} 𝗔𝗗𝗗𝗘𝗗 𝗔𝗦 𝗔𝗗𝗠𝗜𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!</b>", reply_markup=admin_menu())
    except:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗨𝗦𝗘𝗥 𝗜𝗗. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗢𝗡𝗟𝗬.</b>")

@router.callback_query(F.data == "admin_remove")
async def ask_remove_admin(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: 
        return await callback.answer("⛔ 𝗢𝗡𝗟𝗬 𝗦𝗨𝗣𝗘𝗥 𝗔𝗗𝗠𝗜𝗡 𝗖𝗔𝗡 𝗥𝗘𝗠𝗢𝗩𝗘 𝗔𝗗𝗠𝗜𝗡𝗦.", show_alert=True)
    await state.set_state(AdminManageStates.waiting_for_remove_id)
    await callback.message.edit_text("<b>𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗨𝗦𝗘𝗥 𝗜𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗘 𝗙𝗥𝗢𝗠 𝗔𝗗𝗠𝗜𝗡:</b>")

@router.message(AdminManageStates.waiting_for_remove_id)
async def remove_admin(message: Message, state: FSMContext):
    try:
        rem_id = int(message.text.strip())
        if rem_id == ADMIN_ID:
            await state.clear()
            return await message.answer("<b>❌ 𝗬𝗢𝗨 𝗖𝗔𝗡𝗡𝗢𝗧 𝗥𝗘𝗠𝗢𝗩𝗘 𝗧𝗛𝗘 𝗦𝗨𝗣𝗘𝗥 𝗔𝗗𝗠𝗜𝗡!</b>", reply_markup=admin_menu())
        conn = sqlite3.connect("sky_sms.db")
        conn.execute("DELETE FROM admins WHERE user_id=?", (rem_id,))
        conn.commit()
        conn.close()
        await state.clear()
        await message.answer(f"<b>✅ 𝗨𝗦𝗘𝗥 {rem_id} 𝗥𝗘𝗠𝗢𝗩𝗘𝗗 𝗙𝗥𝗢𝗠 𝗔𝗗𝗠𝗜𝗡 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!</b>", reply_markup=admin_menu())
    except:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗨𝗦𝗘𝗥 𝗜𝗗. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗘𝗡𝗧𝗘𝗥 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗢𝗡𝗟𝗬.</b>")

@router.callback_query(F.data == "admin_set_support")
async def ask_support_link(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_support_link)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗟𝗜𝗡𝗞 (e.g., https://t.me/YourUsername):</b>")

@router.message(AdminStates.waiting_for_support_link)
async def save_support_link(message: Message, state: FSMContext):
    set_setting("support_link", message.text.strip())
    await state.clear()
    await message.answer(f"<b>✅ 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗟𝗜𝗡𝗞 𝗦𝗘𝗧 𝗧𝗢: {message.text}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_channel")
async def ask_channel_name(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_channel_name)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗧𝗛𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗡𝗔𝗠𝗘 (e.g., SKY OFFICIAL):</b>")

@router.message(AdminStates.waiting_for_channel_name)
async def ask_channel_link(message: Message, state: FSMContext):
    await state.update_data(channel_name=message.text.upper())
    await state.set_state(AdminStates.waiting_for_channel_link)
    await message.answer("<b>𝗡𝗢𝗪 𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞 (e.g., https://t.me/yourchannel):</b>")

@router.message(AdminStates.waiting_for_channel_link)
async def save_channel_settings(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_name = data['channel_name']
    channel_link = message.text.strip()
    set_setting("force_join_name", channel_name)
    set_setting("force_join_link", channel_link)
    await state.clear()
    await message.answer(f"<b>✅ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗦𝗔𝗩𝗘𝗗!</b>\n\n<b>𝗡𝗔𝗠𝗘:</b> {channel_name}\n<b>𝗟𝗜𝗡𝗞:</b> {channel_link}", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_bkash")
async def ask_bkash_num(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_bkash_num)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗕𝗞𝗔𝗦𝗛 𝗡𝗨𝗠𝗕𝗘𝗥:</b>")

@router.message(AdminStates.waiting_for_bkash_num)
async def save_bkash_num(message: Message, state: FSMContext):
    set_setting("bkash_number", message.text)
    await state.clear()
    await message.answer(f"<b>✅ 𝗕𝗞𝗔𝗦𝗛 𝗡𝗨𝗠𝗕𝗘𝗥 𝗦𝗘𝗧 𝗧𝗢: {message.text}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_nagad")
async def ask_nagad_num(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_nagad_num)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗡𝗔𝗚𝗔𝗗 𝗡𝗨𝗠𝗕𝗘𝗥:</b>")

@router.message(AdminStates.waiting_for_nagad_num)
async def save_nagad_num(message: Message, state: FSMContext):
    set_setting("nagad_number", message.text)
    await state.clear()
    await message.answer(f"<b>✅ 𝗡𝗔𝗚𝗔𝗗 𝗡𝗨𝗠𝗕𝗘𝗥 𝗦𝗘𝗧 𝗧𝗢: {message.text}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_binance")
async def ask_binance_id(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_binance_id)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗬𝗢𝗨𝗥 𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗣𝗔𝗬 𝗜𝗗 (e.g., 123456789):</b>")

@router.message(AdminStates.waiting_for_binance_id)
async def save_binance_id(message: Message, state: FSMContext):
    set_setting("binance_id", message.text)
    await state.clear()
    await message.answer(f"<b>✅ 𝗕𝗜𝗡𝗔𝗡𝗖𝗘 𝗜𝗗 𝗦𝗘𝗧 𝗧𝗢: {message.text}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_min_dep")
async def ask_min_dep(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_min_dep)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗔𝗠𝗢𝗨𝗡𝗧 (e.g., 1.00):</b>")

@router.message(AdminStates.waiting_for_min_dep)
async def save_min_dep(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        set_setting("min_deposit", str(amount))
        await state.clear()
        await message.answer(f"<b>✅ 𝗠𝗜𝗡𝗜𝗠𝗨𝗠 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗦𝗘𝗧 𝗧𝗢: ${amount:.2f}</b>", reply_markup=admin_menu())
    except:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗔𝗠𝗢𝗨𝗡𝗧.</b>")

@router.callback_query(F.data == "admin_set_rate")
async def ask_dollar_rate(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_dollar_rate)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗗𝗢𝗟𝗟𝗔𝗥 𝗥𝗔𝗧𝗘 𝗜𝗡 𝗕𝗗𝗧 (e.g., 130):</b>")

@router.message(AdminStates.waiting_for_dollar_rate)
async def save_dollar_rate(message: Message, state: FSMContext):
    try:
        rate = float(message.text)
        set_setting("dollar_rate", str(rate))
        await state.clear()
        await message.answer(f"<b>✅ 𝗗𝗢𝗟𝗟𝗔𝗥 𝗥𝗔𝗧𝗘 𝗦𝗘𝗧 𝗧𝗢: 𝟭 𝗨𝗦𝗗 = {rate} 𝗕𝗗𝗧</b>", reply_markup=admin_menu())
    except:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗥𝗔𝗧𝗘.</b>")

@router.callback_query(F.data == "admin_add_category")
async def ask_category_name(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_category_name)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗧𝗛𝗘 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 𝗡𝗔𝗠𝗘 (e.g., FACEBOOK):</b>")

@router.message(AdminStates.waiting_for_category_name)
async def ask_category_icon(message: Message, state: FSMContext):
    await state.update_data(cat_name=message.text.upper())
    await state.set_state(AdminStates.waiting_for_category_icon)
    await message.answer("<b>𝗡𝗢𝗪 𝗦𝗘𝗡𝗗 𝗔𝗡 𝗘𝗠𝗢𝗝𝗜/𝗟𝗢𝗚𝗢 𝗙𝗢𝗥 𝗧𝗛𝗜𝗦 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 (e.g., 🔵 or 📘):</b>")

@router.message(AdminStates.waiting_for_category_icon)
async def save_category(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_name = data['cat_name']
    cat_icon = message.text.strip()
    conn = sqlite3.connect("sky_sms.db")
    conn.execute("INSERT OR REPLACE INTO categories (name, icon) VALUES (?, ?)", (cat_name, cat_icon))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(f"<b>✅ 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 '{cat_name}' 𝗔𝗗𝗗𝗘𝗗 𝗪𝗜𝗧𝗛 𝗜𝗖𝗢𝗡 {cat_icon}!</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_broadcast")
async def ask_broadcast_msg(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text("<b>📣 𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗢𝗥 𝗠𝗘𝗗𝗜𝗔 𝗬𝗢𝗨 𝗪𝗔𝗡𝗧 𝗧𝗢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧:</b>")

@router.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: Message, state: FSMContext):
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    conn.close()
    success, failed = 0, 0
    await message.answer(f"<b>⏳ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧𝗜𝗡𝗚 𝗧𝗢 {len(users)} 𝗨𝗦𝗘𝗥𝗦...</b>")
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            success += 1
            await asyncio.sleep(0.05)
        except: failed += 1
    await state.clear()
    await message.answer(f"<b>✅ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘!</b>\n\n<b>𝗦𝗨𝗖𝗖𝗘𝗦𝗦: {success}</b>\n<b>𝗙𝗔𝗜𝗟𝗘𝗗: {failed}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_set_cooldown")
async def ask_cooldown(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_cooldown_time)
    await callback.message.edit_text("<b>𝗘𝗡𝗧𝗘𝗥 𝗖𝗢𝗢𝗟𝗗𝗢𝗪𝗡 𝗧𝗜𝗠𝗘 𝗜𝗡 𝗦𝗘𝗖𝗢𝗡𝗗𝗦:</b>")

@router.message(AdminStates.waiting_for_cooldown_time)
async def save_cooldown(message: Message, state: FSMContext):
    if message.text.isdigit():
        set_setting("cooldown_seconds", message.text)
        await state.clear()
        await message.answer(f"<b>✅ 𝗖𝗢𝗢𝗟𝗗𝗢𝗪𝗡 𝗦𝗘𝗧 𝗧𝗢 {message.text} 𝗦𝗘𝗖𝗢𝗡𝗗𝗦.</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_upload_start")
async def admin_upload_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text(f"<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 𝗙𝗢𝗥 𝗨𝗣𝗟𝗢𝗔𝗗:</b>\n\n<b>𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗟𝗜𝗩𝗘 𝗦𝗧𝗢𝗖𝗞: {get_stock_count()}</b>", reply_markup=category_selection_menu("upload_cat"))

@router.callback_query(F.data.startswith("upload_cat_"))
async def ask_for_txt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    category = callback.data.split("_")[2]
    await state.update_data(upload_category=category)
    await state.set_state(AdminStates.waiting_for_txt_file)
    await callback.message.edit_text(f"<b>📥 𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗔 .𝗧𝗫𝗧 𝗙𝗜𝗟𝗘 𝗙𝗢𝗥 {category}.</b>\n\n<b>(𝗢𝗡𝗘 𝗡𝗨𝗠𝗕𝗘𝗥 𝗣𝗘𝗥 𝗟𝗜𝗡𝗘)</b>")

@router.message(AdminStates.waiting_for_txt_file, F.document)
async def handle_txt_upload(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.endswith('.txt'):
        return await message.answer("<b>❌ 𝗢𝗡𝗟𝗬 .𝗧𝗫𝗧 𝗙𝗜𝗟𝗘𝗦 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!</b>")
    file_path = f"downloads/{doc.file_id}.txt"
    os.makedirs("downloads", exist_ok=True)
    await message.bot.download(doc, destination=file_path)
    
    data = await state.get_data()
    category = data['upload_category']
    
    added = 0
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    
    default_price = float(get_setting("default_price", "0.0000"))
    
    with open(file_path, 'r') as f:
        for line in f:
            num_str = line.strip().replace("+", "")
            if not num_str: continue
            
            country_name, flag = get_country_info(num_str)
            
            cur.execute("""INSERT OR IGNORE INTO numbers 
                (number, service_category, country_name, country_flag, price, status) 
                VALUES (?, ?, ?, ?, ?, 'AVAILABLE')""",
                (num_str, category, country_name, flag, default_price))
            if cur.rowcount > 0: added += 1
    conn.commit()
    conn.close()
    os.remove(file_path)
    await state.clear()
    await message.answer(f"<b>✅ 𝗦𝗨𝗖𝗖𝗘𝗦𝗦! 𝗔𝗗𝗗𝗘𝗗 {added} 𝗡𝗨𝗠𝗕𝗘𝗥𝗦 𝗧𝗢 {category} 𝗦𝗧𝗢𝗖𝗞.</b>\n<b>𝗧𝗢𝗧𝗔𝗟 𝗟𝗜𝗩𝗘 𝗦𝗧𝗢𝗖𝗞: {get_stock_count()}</b>", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_assign_number")
async def ask_assign_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_assign_user)
    await callback.message.edit_text("<b>𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗨𝗦𝗘𝗥 𝗜𝗗 𝗧𝗢 𝗔𝗦𝗦𝗜𝗚𝗡 𝗔 𝗡𝗨𝗠𝗕𝗘𝗥:</b>")

@router.message(AdminStates.waiting_for_assign_user)
async def ask_assign_number(message: Message, state: FSMContext):
    await state.update_data(target_user=message.text)
    await state.set_state(AdminStates.waiting_for_assign_number)
    await message.answer("<b>𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗡𝗨𝗠𝗕𝗘𝗥 (𝗪𝗜𝗧𝗛 𝗢𝗥 𝗪𝗜𝗧𝗛𝗢𝗨𝗧 '+'):</b>")

@router.message(AdminStates.waiting_for_assign_number)
async def save_assigned_number(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user = data['target_user']
    raw_number = message.text.strip().replace("+", "")
    try:
        conn = sqlite3.connect("sky_sms.db")
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO numbers (number, service_category, country_name, country_flag, price, status) VALUES (?, 'CUSTOM', 'CUSTOM', '🌍', 0.0, 'IN_USE')", (raw_number,))
        num_id = cur.lastrowid
        cur.execute("INSERT INTO orders (user_id, number_id, status, created_at) VALUES (?, ?, 'PENDING', ?)", (target_user, num_id, datetime.datetime.now()))
        order_id = cur.lastrowid
        conn.commit()
        conn.close()
        await state.clear()
        await message.answer(f"<b>✅ 𝗡𝗨𝗠𝗕𝗘𝗥 +{raw_number} 𝗔𝗦𝗦𝗜𝗚𝗡𝗘𝗗 𝗧𝗢 𝗨𝗦𝗘𝗥 {target_user}.</b>", reply_markup=admin_menu())
        try:
            await bot.send_message(target_user, f"🎁 <b>𝗔𝗗𝗠𝗜𝗡 𝗔𝗦𝗦𝗜𝗚𝗡𝗘𝗗 𝗔 𝗡𝗨𝗠𝗕𝗘𝗥 𝗧𝗢 𝗬𝗢𝗨:</b>\n\n🌍 <code>+{raw_number}</code>\n\n⏳ <b>𝗪𝗔𝗜𝗧𝗜𝗡𝗚 𝗙𝗢𝗥 𝗢𝗧𝗣...</b>", reply_markup=order_menu(order_id, 0.0, "CUSTOM"))
        except: pass
    except Exception as e:
        await message.answer(f"<b>❌ 𝗘𝗥𝗥𝗢𝗥: {e}</b>")

@router.callback_query(F.data == "admin_manage_balance")
async def ask_bal_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_bal_user)
    await callback.message.edit_text("<b>💰 𝗘𝗡𝗧𝗘𝗥 𝗧𝗛𝗘 𝗨𝗦𝗘𝗥 𝗜𝗗 𝗧𝗢 𝗠𝗔𝗡𝗔𝗚𝗘 𝗕𝗔𝗟𝗔𝗡𝗖𝗘:</b>")

@router.message(AdminStates.waiting_for_bal_user)
async def show_user_info_for_balance(message: Message, state: FSMContext):
    target_user = message.text.strip()
    conn = sqlite3.connect("sky_sms.db")
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (target_user,))
    user_data = cur.fetchone()
    conn.close()
    if not user_data:
        return await message.answer("<b>❌ 𝗨𝗦𝗘𝗥 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗! 𝗧𝗥𝗬 𝗔𝗚𝗔𝗜𝗡:</b>")
    current_balance = user_data[0]
    await state.update_data(target_user=target_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="<b>➕ 𝗔𝗗𝗗 𝗠𝗢𝗡𝗘𝗬</b>", callback_data=f"bal_add_{target_user}", style="success"),
         InlineKeyboardButton(text="<b>➖ 𝗦𝗨𝗕𝗧𝗥𝗔𝗖𝗧 𝗠𝗢𝗡𝗘𝗬</b>", callback_data=f"bal_sub_{target_user}", style="danger")],
        [InlineKeyboardButton(text="<b>🔙 𝗖𝗔𝗡𝗖𝗘𝗟</b>", callback_data="admin_panel", style="danger")]
    ])
    await message.answer(
        f"👤 <b>𝗨𝗦𝗘𝗥 𝗜𝗗: {target_user}</b>\n"
        f"💰 <b>𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${current_balance:.4f}</b>\n\n"
        f"<b>𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗖𝗧𝗜𝗢𝗡:</b>",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("bal_add_"))
async def ask_add_amount(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    user_id = callback.data.split("_")[2]
    await state.update_data(target_user=user_id, action="ADD")
    await state.set_state(AdminStates.waiting_for_bal_amount)
    await callback.message.edit_text(f"<b>➕ 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧 𝗧𝗢 𝗔𝗗𝗗 𝗧𝗢 𝗨𝗦𝗘𝗥 {user_id}:</b>")

@router.callback_query(F.data.startswith("bal_sub_"))
async def ask_sub_amount(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    user_id = callback.data.split("_")[2]
    await state.update_data(target_user=user_id, action="SUB")
    await state.set_state(AdminStates.waiting_for_bal_amount)
    await callback.message.edit_text(f"<b>➖ 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧 𝗧𝗢 𝗦𝗨𝗕𝗧𝗥𝗔𝗖𝗧 𝗙𝗥𝗢𝗠 𝗨𝗦𝗘𝗥 {user_id}:</b>")

@router.message(AdminStates.waiting_for_bal_amount)
async def save_balance_change(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user = data['target_user']
    action = data['action']
    try:
        amount = float(message.text)
        if amount <= 0: raise ValueError
        conn = sqlite3.connect("sky_sms.db")
        cur = conn.cursor()
        if action == "ADD":
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_user))
        else:
            cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, target_user))
        conn.commit()
        cur.execute("SELECT balance FROM users WHERE user_id=?", (target_user,))
        new_balance = cur.fetchone()[0]
        conn.close()
        await state.clear()
        action_text = "𝗔𝗗𝗗𝗘𝗗 𝗧𝗢" if action == "ADD" else "𝗦𝗨𝗕𝗧𝗥𝗔𝗖𝗧𝗘𝗗 𝗙𝗥𝗢𝗠"
        await message.answer(f"<b>✅ 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬 {action_text} 𝗨𝗦𝗘𝗥 {target_user}!</b>\n💰 <b>𝗡𝗘𝗪 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${new_balance:.4f}</b>", reply_markup=admin_menu())
        try:
            if action == "ADD":
                await bot.send_message(target_user, f"🎉 <b>𝗔𝗗𝗠𝗜𝗡 𝗔𝗗𝗗𝗘𝗗 ${amount:.4f} 𝗧𝗢 𝗬𝗢𝗨𝗥 𝗪𝗔𝗟𝗟𝗘𝗧!</b>\n💰 <b>𝗡𝗘𝗪 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${new_balance:.4f}</b>")
            else:
                await bot.send_message(target_user, f"⚠️ <b>𝗔𝗗𝗠𝗜𝗡 𝗦𝗨𝗕𝗧𝗥𝗔𝗖𝗧𝗘𝗗 ${amount:.4f} 𝗙𝗥𝗢𝗠 𝗬𝗢𝗨𝗥 𝗪𝗔𝗟𝗟𝗘𝗧!</b>\n💰 <b>𝗡𝗘𝗪 𝗕𝗔𝗟𝗔𝗡𝗖𝗘: ${new_balance:.4f}</b>")
        except: pass
    except:
        await message.answer("<b>❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗔𝗠𝗢𝗨𝗡𝗧.</b>")

# ==========================================
# বট রান
# ==========================================
async def main():
    logging.info("SKY SMS BOT IS RUNNING...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

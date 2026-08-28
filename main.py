import asyncio
import re
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from typing import Callable, Dict, Any, Awaitable
import database

# টোকেন ও অ্যাডমিন আইডি
BOT_TOKEN = "8941233684:AAEA6RGrFfCyzPpiqfAa4QbeevfLl_4nb5U"
ADMIN_ID = 8383532004

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db_pool = None

# ================= STATES =================
class MemberReg(StatesGroup):
    waiting_for_id = State()
    waiting_for_phone = State()
    confirming_profile = State()
    waiting_for_meme = State()

class MemeSubmit(StatesGroup):
    confirming_meme = State()

class AdminSettings(StatesGroup):
    waiting_for_numbers = State()
    waiting_for_ids = State()
    waiting_for_mod_name = State()
    waiting_for_new_pass = State()

# ================= MIDDLEWARE =================
class GlobalCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user and user.id != ADMIN_ID:
            # চেক করা মডারেটর বা মেম্বার ব্লক কি না
            user_rec = await database.get_user(db_pool, user.id)
            if user_rec and user_rec.get('is_blocked'):
                if isinstance(event, types.Message):
                    await event.answer("Access Blocked⛔")
                elif isinstance(event, types.CallbackQuery):
                    await event.answer("Access Blocked⛔", show_alert=True)
                return

            is_on = await database.get_event_status(db_pool)
            if not is_on:
                if isinstance(event, types.Message):
                    await event.answer("Event End!")
                elif isinstance(event, types.CallbackQuery):
                    await event.answer("Event End!", show_alert=True)
                return
        return await handler(event, data)

dp.message.middleware(GlobalCheckMiddleware())
dp.callback_query.middleware(GlobalCheckMiddleware())

# ================= 1. MEMBER VIEW =================
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await send_admin_panel(message.chat.id)
        return
        
    user = await database.get_user(db_pool, message.from_user.id)
    if user:
        if user['is_blocked']:
            await message.answer("Access Blocked⛔")
            return
        if user['role'] == 'MODERATOR':
            await send_mod_panel(message.chat.id)
            return
        elif user['role'] == 'MEMBER':
            count = await database.get_meme_count(db_pool, message.from_user.id)
            if count >= 5:
                kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Refresh Status🔃")]], resize_keyboard=True)
                await message.answer("Your limit is over. You have successfully submitted 5 Memes. Please wait for the results♥️", reply_markup=kb)
            else:
                await message.answer("আপনি ইতিমধ্যে নিবন্ধিত! Meme সাবমিট করতে পারেন।", reply_markup=ReplyKeyboardRemove())
                await state.set_state(MemberReg.waiting_for_meme)
            return

    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Registration"), KeyboardButton(text="Already Registered")]
    ], resize_keyboard=True)
    await message.answer("Welcome To KBKh Moderator Selection Zone!", reply_markup=kb)

@dp.message(F.text == "Registration")
async def start_registration(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
    await message.answer("Please enter your unique ID:", reply_markup=kb)
    await state.set_state(MemberReg.waiting_for_id)

@dp.message(F.text == "Cancel")
async def process_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Process Cancelled✅", reply_markup=ReplyKeyboardRemove())
    await start_cmd(message, state)

@dp.message(MemberReg.waiting_for_id)
async def process_id(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        return await process_cancel(message, state)
        
    unique_id = message.text.replace(" ", "").upper()
    is_valid = await database.check_valid_unique_id(db_pool, unique_id)
    
    if is_valid:
        await state.update_data(unique_id=unique_id)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
        await message.answer("Valid Unique ID✅\n\nPlease enter Mobile Number:", reply_markup=kb)
        await state.set_state(MemberReg.waiting_for_phone)
    else:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
        await message.answer("Invalid Unique ID❌\nPlease enter the correct unique ID:", reply_markup=kb)

def format_phone(p):
    raw = p.replace("-", "").replace(" ", "").replace("+", "")
    if raw.startswith("8801") and len(raw) == 13:
        raw = raw[2:]
    elif len(raw) == 10 and raw.startswith("1"):
        raw = "0" + raw
    return raw

@dp.message(MemberReg.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        return await process_cancel(message, state)

    raw_phone = format_phone(message.text)
    
    if raw_phone.isdigit():
        data = await state.get_data()
        is_matched = await database.check_phone_for_id(db_pool, data['unique_id'], raw_phone)
        
        if is_matched:
            await state.update_data(phone=raw_phone)
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Submit"), KeyboardButton(text="Cancel")]], resize_keyboard=True)
            text = f"🎫Final Registration\n\nUnique ID: {data['unique_id']}\nMobile Number: {raw_phone}\n\nPlease confirm your information and then press submit!"
            await message.answer(text, reply_markup=kb)
            await state.set_state(MemberReg.confirming_profile)
            return
            
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
    await message.answer("Invalid Number❌\nPlease enter the correct Number:", reply_markup=kb)

@dp.message(MemberReg.confirming_profile)
async def submit_profile(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        return await process_cancel(message, state)
    if message.text == "Submit":
        data = await state.get_data()
        await database.register_user(db_pool, message.from_user.id, data['unique_id'], data['phone'], 'MEMBER')
        await message.answer("Registration Complete✅\nএখন আপনি প্রতিযোগিতার জন্য প্রয়োজনীয় মিমস এখানে সরাসরি সাবমিট করতে পারেন।", reply_markup=ReplyKeyboardRemove())
        await state.set_state(MemberReg.waiting_for_meme)

@dp.message(F.text == "Already Registered")
async def already_registered(message: types.Message, state: FSMContext):
    user = await database.get_user(db_pool, message.from_user.id)
    if user:
        if user['is_blocked']:
            await message.answer("Access Blocked⛔")
            return
        count = await database.get_meme_count(db_pool, message.from_user.id)
        if count >= 5:
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Refresh Status🔃")]], resize_keyboard=True)
            await message.answer("Your limit is over. You have successfully submitted 5 Memes. Please wait for the results♥️", reply_markup=kb)
        else:
            await message.answer("আপনি ইতিমধ্যে নিবন্ধিত! Meme সাবমিট করতে পারেন।", reply_markup=ReplyKeyboardRemove())
            await state.set_state(MemberReg.waiting_for_meme)
    else:
        await message.answer("আপনি এখনও রেজিস্ট্রেশন করেননি। Registration বাটনে চাপ দিন।")

@dp.message(F.text == "Refresh Status🔃")
async def handle_refresh_status(message: types.Message, state: FSMContext):
    user = await database.get_user(db_pool, message.from_user.id)
    if not user:
        return await start_cmd(message, state)
    await message.answer("Your limit is over. You have successfully submitted 5 Memes. Please wait for the results♥️")

@dp.message(F.photo, MemberReg.waiting_for_meme)
async def receive_meme(message: types.Message, state: FSMContext):
    user = await database.get_user(db_pool, message.from_user.id)
    if not user:
        return await start_cmd(message, state)

    count = await database.get_meme_count(db_pool, message.from_user.id)
    if count >= 5:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Refresh Status🔃")]], resize_keyboard=True)
        await message.answer("Your limit is over. You have successfully submitted 5 Memes. Please wait for the results♥️", reply_markup=kb)
        return

    await state.set_state(MemeSubmit.confirming_meme)
    await state.update_data(temp_file_id=message.photo[-1].file_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes✅", callback_data="meme_yes"), InlineKeyboardButton(text="No❌", callback_data="meme_no")]
    ])
    await message.answer("Are you sure you want to submit this meme for moderator selection?", reply_markup=kb)

@dp.message(F.photo, MemeSubmit.confirming_meme)
async def block_multiple_memes(message: types.Message):
    await message.answer("একসাথে একাধিক মিম সাবমিট করা যাবে না। একটি করে মিম সাবমিট করুন। তাড়াহুড়ো করা যাবে না!")

@dp.callback_query(F.data.startswith("meme_"))
async def confirm_meme(cq: types.CallbackQuery, state: FSMContext):
    user = await database.get_user(db_pool, cq.from_user.id)
    if not user:
        await cq.message.delete()
        await state.clear()
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Registration"), KeyboardButton(text="Already Registered")]], resize_keyboard=True)
        return await bot.send_message(cq.from_user.id, "Welcome To KBKh Moderator Selection Zone!", reply_markup=kb)

    if cq.data == "meme_no":
        await cq.message.edit_text("Process Cancelled✅")
        await state.set_state(MemberReg.waiting_for_meme)
        return

    data = await state.get_data()
    file_id = data.get('temp_file_id')
    await database.add_meme(db_pool, cq.from_user.id, file_id)
    
    count = await database.get_meme_count(db_pool, cq.from_user.id)
    left = 5 - count
    
    if left > 0:
        await cq.message.edit_text(f"Submitted successfully✅\n\nYou can submit up to {left} more memes!")
        await state.set_state(MemberReg.waiting_for_meme)
    else:
        await cq.message.edit_text("You have successfully submitted a total of 5 memes✅")
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Refresh Status🔃")]], resize_keyboard=True)
        await bot.send_message(cq.from_user.id, "Your limit is over. Wait for the result. Thank you!♥️", reply_markup=kb)
        await state.clear()

# ================= 2. MODERATOR LOGIN & VIEW =================
class ModPassFilter(Filter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.text: return False
        current_pass = await database.get_mod_password(db_pool)
        return message.text == current_pass

@dp.message(ModPassFilter())
async def check_mod_login(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        return
        
    user = await database.get_user(db_pool, message.from_user.id)
    if user and user.get('name'):
        await database.register_user(db_pool, message.from_user.id, user['unique_id'], user['phone_number'], 'MODERATOR')
        await message.answer("Welcome Sir!\nYou are now in the main panel.")
        await send_mod_panel(message.chat.id)
    else:
        await state.set_state(AdminSettings.waiting_for_mod_name)
        await message.answer("Valid Id✅\nPlease Enter Your Name:")

@dp.message(AdminSettings.waiting_for_mod_name)
async def save_mod_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await database.register_user(db_pool, message.from_user.id, f"MOD_{message.from_user.id}", "N/A", "MODERATOR", name=name)
    await state.clear()
    await message.answer("Welcome Sir!\nYou are now in the main panel.")
    await send_mod_panel(message.chat.id)

async def send_mod_panel(chat_id):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Pending Marking"), KeyboardButton(text="Already Marked")]
    ], resize_keyboard=True)
    await bot.send_message(chat_id, "Please select an option:", reply_markup=kb)

@dp.message(F.text == "Pending Marking")
async def show_pending(message: types.Message, state: FSMContext):
    user = await database.get_user(db_pool, message.from_user.id)
    if not user or user['role'] != 'MODERATOR':
        return await start_cmd(message, state)

    candidates = await database.get_pending_candidates(db_pool, message.from_user.id)
    if not candidates:
        return await message.answer("No memes pending for marking!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{c['unique_id']} - {c['pending_count']}", callback_data=f"mod_cand_false_{c['unique_id']}")]
        for c in candidates
    ])
    await message.answer("Candidates\n", reply_markup=kb)

@dp.message(F.text == "Already Marked")
async def show_marked(message: types.Message, state: FSMContext):
    user = await database.get_user(db_pool, message.from_user.id)
    if not user or user['role'] != 'MODERATOR':
        return await start_cmd(message, state)

    candidates = await database.get_marked_candidates(db_pool, message.from_user.id)
    if not candidates:
        return await message.answer("No memes marked yet!")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{c['unique_id']} - {c['marked_count']}🔺", callback_data=f"mod_expand_{c['unique_id']}")]
        for c in candidates
    ])
    await message.answer("Candidates\n", reply_markup=kb)

@dp.callback_query(F.data.startswith("mod_expand_"))
async def expand_marked(cq: types.CallbackQuery):
    unique_id = cq.data.split("_")[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{unique_id} 🔻", callback_data=f"mod_collapse_{unique_id}")],
        [InlineKeyboardButton(text="Remark", callback_data=f"mod_cand_true_{unique_id}")]
    ])
    await cq.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("mod_collapse_"))
async def collapse_marked(cq: types.CallbackQuery):
    unique_id = cq.data.split("_")[2]
    candidates = await database.get_marked_candidates(db_pool, cq.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{c['unique_id']} - {c['marked_count']}🔺", callback_data=f"mod_expand_{c['unique_id']}")]
        for c in candidates
    ])
    await cq.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("mod_cand_"))
async def show_candidate_memes(cq: types.CallbackQuery):
    _, _, is_marked_str, unique_id = cq.data.split("_")
    is_marked = is_marked_str == "true"
    
    memes = await database.get_memes_for_candidate(db_pool, cq.from_user.id, unique_id, is_marked)
    
    for meme in memes:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1", callback_data=f"mark_1_{meme['meme_id']}"),
             InlineKeyboardButton(text="2", callback_data=f"mark_2_{meme['meme_id']}"),
             InlineKeyboardButton(text="3", callback_data=f"mark_3_{meme['meme_id']}"),
             InlineKeyboardButton(text="4", callback_data=f"mark_4_{meme['meme_id']}"),
             InlineKeyboardButton(text="5", callback_data=f"mark_5_{meme['meme_id']}")],
            [InlineKeyboardButton(text="Submit", callback_data=f"submit_mark_{meme['meme_id']}"),
             InlineKeyboardButton(text="Cancel", callback_data=f"cancel_mark_{meme['meme_id']}")]
        ])
        caption = f"{unique_id}\n(Select mark first, then Submit)" if not is_marked else f"{unique_id}\n(Previous Mark: {meme['mark']})"
        await bot.send_photo(cq.message.chat.id, photo=meme['file_id'], caption=caption, reply_markup=kb)
    
    await cq.answer()

@dp.callback_query(F.data.startswith("mark_"))
async def select_mark(cq: types.CallbackQuery):
    _, mark, meme_id = cq.data.split("_")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1" + ("✅" if mark=="1" else ""), callback_data=f"mark_1_{meme_id}"),
         InlineKeyboardButton(text="2" + ("✅" if mark=="2" else ""), callback_data=f"mark_2_{meme_id}"),
         InlineKeyboardButton(text="3" + ("✅" if mark=="3" else ""), callback_data=f"mark_3_{meme_id}"),
         InlineKeyboardButton(text="4" + ("✅" if mark=="4" else ""), callback_data=f"mark_4_{meme_id}"),
         InlineKeyboardButton(text="5" + ("✅" if mark=="5" else ""), callback_data=f"mark_5_{meme_id}")],
        [InlineKeyboardButton(text="Submit", callback_data=f"submit_mark_{meme_id}_{mark}"),
         InlineKeyboardButton(text="Cancel", callback_data=f"cancel_mark_{meme_id}")]
    ])
    await cq.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("submit_mark_"))
async def finalize_mark(cq: types.CallbackQuery):
    user = await database.get_user(db_pool, cq.from_user.id)
    if not user or user['role'] != 'MODERATOR':
        await cq.message.delete()
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Registration"), KeyboardButton(text="Already Registered")]], resize_keyboard=True)
        return await bot.send_message(cq.from_user.id, "Welcome To KBKh Moderator Selection Zone!", reply_markup=kb)

    parts = cq.data.split("_")
    if len(parts) < 4:
        return await cq.answer("Please select a mark (1-5) first!", show_alert=True)
    
    meme_id = int(parts[2])
    mark = int(parts[3])
    
    await database.mark_meme(db_pool, meme_id, mark)
    await cq.message.delete()
    await cq.message.answer("Marking Done✅")

@dp.callback_query(F.data.startswith("cancel_mark_"))
async def cancel_mark(cq: types.CallbackQuery):
    await cq.message.delete()
    await cq.message.answer("Process Cancelled✅")

# ================= 3. ADMIN VIEW & REGISTERED MEMBERS =================
async def send_admin_panel(chat_id):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Result")],
        [KeyboardButton(text="On/Off🔺"), KeyboardButton(text="Insert Data🔺")],
        [KeyboardButton(text="Registered Members")],
        [KeyboardButton(text="Reset All Data"), KeyboardButton(text="Publish Result")]
    ], resize_keyboard=True)
    await bot.send_message(chat_id, "Admin Panel Options:", reply_markup=kb)

@dp.message(F.text == "On/Off🔺")
async def toggle_menu(message: types.Message):
    is_on = await database.get_event_status(db_pool)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=f"On{' 🟢' if is_on else ''}")],
        [KeyboardButton(text=f"Off{' 🔴' if not is_on else ''}")],
        [KeyboardButton(text="Back")]
    ], resize_keyboard=True)
    await message.answer("On/Off🔻", reply_markup=kb)

@dp.message(F.text.in_({"On", "On 🟢", "Off", "Off 🔴"}))
async def set_on_off(message: types.Message):
    status = "On" in message.text
    await database.toggle_event_status(db_pool, status)
    await toggle_menu(message)

@dp.message(F.text == "Insert Data🔺")
async def insert_menu(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Number"), KeyboardButton(text="Unique ID")],
        [KeyboardButton(text="Back")]
    ], resize_keyboard=True)
    await message.answer("Insert Data🔻", reply_markup=kb)

@dp.message(F.text == "Number")
async def ask_number(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
    await message.answer("Please Input Numbers:\n(Send multiple numbers separated by new line)", reply_markup=kb)
    await state.set_state(AdminSettings.waiting_for_numbers)

@dp.message(F.text == "Unique ID")
async def ask_ids(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Cancel")]], resize_keyboard=True)
    await message.answer("Please Input Unique ID:\n(Send multiple IDs separated by new line)", reply_markup=kb)
    await state.set_state(AdminSettings.waiting_for_ids)

@dp.message(AdminSettings.waiting_for_numbers)
async def save_numbers(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        await state.clear()
        await message.answer("Process Cancelled✅")
        return await send_admin_panel(message.chat.id)
        
    nums = [format_phone(n.strip()) for n in message.text.split("\n") if n.strip()]
    await database.insert_paired_numbers(db_pool, nums)
    await state.clear()
    await message.answer("Number successfully added to Database✅")
    await send_admin_panel(message.chat.id)

@dp.message(AdminSettings.waiting_for_ids)
async def save_ids(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        await state.clear()
        await message.answer("Process Cancelled✅")
        return await send_admin_panel(message.chat.id)
        
    ids = [i.strip().upper() for i in message.text.split("\n") if i.strip()]
    await database.insert_paired_ids(db_pool, ids)
    await state.clear()
    await message.answer("Unique ID successfully added to Database✅")
    await send_admin_panel(message.chat.id)

@dp.message(F.text == "Back")
async def back_to_admin(message: types.Message):
    await send_admin_panel(message.chat.id)

# ---- 1. RESET ALL DATA OPTIONS ----
@dp.message(F.text == "Reset All Data")
async def confirm_reset_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Inserted Data", callback_data="reset_opt_inserted"),
         InlineKeyboardButton(text="All Data", callback_data="reset_opt_all")],
        [InlineKeyboardButton(text="Cancel", callback_data="reset_opt_cancel")]
    ])
    await message.answer("Select Reset Option:", reply_markup=kb)

@dp.callback_query(F.data == "reset_opt_inserted")
async def reset_inserted_confirm(cq: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes✅", callback_data="reset_ins_yes"), InlineKeyboardButton(text="No❌", callback_data="reset_ins_no")]
    ])
    await cq.message.edit_text("Are you sure you want to reset all Numbers & Unique ID Data?", reply_markup=kb)

@dp.callback_query(F.data == "reset_ins_yes")
async def execute_reset_inserted(cq: types.CallbackQuery):
    await database.reset_inserted_data(db_pool)
    await cq.message.edit_text("Inserted Data reset successfully✅")

@dp.callback_query(F.data == "reset_ins_no")
async def back_to_reset_menu(cq: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Inserted Data", callback_data="reset_opt_inserted"),
         InlineKeyboardButton(text="All Data", callback_data="reset_opt_all")],
        [InlineKeyboardButton(text="Cancel", callback_data="reset_opt_cancel")]
    ])
    await cq.message.edit_text("Select Reset Option:", reply_markup=kb)

@dp.callback_query(F.data == "reset_opt_all")
async def reset_all_confirm(cq: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes✅", callback_data="reset_all_yes"), InlineKeyboardButton(text="No❌", callback_data="reset_all_no")]
    ])
    await cq.message.edit_text("Are you sure you want to reset ALL data?", reply_markup=kb)

@dp.callback_query(F.data == "reset_all_yes")
async def execute_reset_all(cq: types.CallbackQuery):
    await database.reset_all_data(db_pool)
    await cq.message.edit_text("All data reset successfully✅")

@dp.callback_query(F.data.in_({"reset_all_no", "reset_opt_cancel"}))
async def cancel_reset_menu(cq: types.CallbackQuery):
    await cq.message.delete()
    await cq.message.answer("Process Cancelled✅")

# ---- 2. REGISTERED MEMBERS / MODERATORS MANAGEMENT ----
@dp.message(F.text == "Registered Members")
async def registered_members_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Moderators", callback_data="reg_mod_list"),
         InlineKeyboardButton(text="Members", callback_data="reg_mem_list")],
        [InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")]
    ])
    await message.answer("Select category to manage:", reply_markup=kb)

@dp.callback_query(F.data == "reg_cancel")
async def cancel_reg_menu(cq: types.CallbackQuery, state: FSMContext):
    await state.update_data(pending_actions={})
    await cq.message.delete()
    await cq.message.answer("Process Cancelled✅")

@dp.callback_query(F.data == "reg_back")
async def reg_back_handler(cq: types.CallbackQuery, state: FSMContext):
    await state.update_data(pending_actions={})
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Moderators", callback_data="reg_mod_list"),
         InlineKeyboardButton(text="Members", callback_data="reg_mem_list")],
        [InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")]
    ])
    await cq.message.edit_text("Select category to manage:", reply_markup=kb)

@dp.callback_query(F.data == "reg_mod_list")
async def show_moderators_list(cq: types.CallbackQuery, state: FSMContext):
    mods = await database.get_all_moderators(db_pool)
    if not mods:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Change Pass", callback_data="reg_change_pass")],
            [InlineKeyboardButton(text="Back", callback_data="reg_back"), InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")]
        ])
        return await cq.message.edit_text("Moderators:\nNo moderators registered yet.", reply_markup=kb)

    data = await state.get_data()
    pending = data.get('pending_actions', {})

    inline_kb = []
    for m in mods:
        tg_id_str = str(m['telegram_id'])
        name = m['name'] or m['unique_id']
        pend_act = pending.get(tg_id_str)
        
        b_icon = "🟢" if m['is_blocked'] else "⛔"
        if pend_act == 'block': b_icon += "(selected)"
        r_icon = "❌(selected)" if pend_act == 'remove' else "❌"
        
        inline_kb.append([
            InlineKeyboardButton(text=name, callback_data="noop"),
            InlineKeyboardButton(text=b_icon, callback_data=f"act_b_{m['telegram_id']}_mod"),
            InlineKeyboardButton(text=r_icon, callback_data=f"act_r_{m['telegram_id']}_mod")
        ])
    
    inline_kb.append([InlineKeyboardButton(text="Submit", callback_data="reg_exec_mod")])
    inline_kb.append([InlineKeyboardButton(text="Change Pass", callback_data="reg_change_pass")])
    inline_kb.append([InlineKeyboardButton(text="Back", callback_data="reg_back"), InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")])
    
    await cq.message.edit_text("Moderators:\n", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))

@dp.callback_query(F.data == "reg_mem_list")
async def show_members_list(cq: types.CallbackQuery, state: FSMContext):
    mems = await database.get_all_members(db_pool)
    if not mems:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data="reg_back"), InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")]
        ])
        return await cq.message.edit_text("Members:\nNo members registered yet.", reply_markup=kb)

    data = await state.get_data()
    pending = data.get('pending_actions', {})

    inline_kb = []
    for mem in mems:
        tg_id_str = str(mem['telegram_id'])
        uid = mem['unique_id']
        pend_act = pending.get(tg_id_str)
        
        b_icon = "🟢" if mem['is_blocked'] else "⛔"
        if pend_act == 'block': b_icon += "(selected)"
        r_icon = "❌(selected)" if pend_act == 'remove' else "❌"
        
        inline_kb.append([
            InlineKeyboardButton(text=uid, callback_data="noop"),
            InlineKeyboardButton(text=b_icon, callback_data=f"act_b_{mem['telegram_id']}_mem"),
            InlineKeyboardButton(text=r_icon, callback_data=f"act_r_{mem['telegram_id']}_mem")
        ])
    
    inline_kb.append([InlineKeyboardButton(text="Submit", callback_data="reg_exec_mem")])
    inline_kb.append([InlineKeyboardButton(text="Back", callback_data="reg_back"), InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")])
    
    await cq.message.edit_text("Members:\n", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))

@dp.callback_query(F.data == "noop")
async def noop_cb(cq: types.CallbackQuery):
    await cq.answer()

@dp.callback_query(F.data.startswith("act_"))
async def select_action(cq: types.CallbackQuery, state: FSMContext):
    parts = cq.data.split("_")
    act_type = 'block' if parts[1] == 'b' else 'remove'
    tg_id_str = parts[2]
    list_type = parts[3]
    
    data = await state.get_data()
    pending = data.get('pending_actions', {})
    
    # Toggle logic: if already selected, remove selection. Otherwise set/overwrite selection.
    if pending.get(tg_id_str) == act_type:
        del pending[tg_id_str]
    else:
        pending[tg_id_str] = act_type
        
    await state.update_data(pending_actions=pending)
    
    if list_type == 'mod':
        await show_moderators_list(cq, state)
    else:
        await show_members_list(cq, state)

@dp.callback_query(F.data.startswith("reg_exec_"))
async def execute_pending_actions(cq: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pending = data.get('pending_actions', {})
    
    for tg_id_str, action in pending.items():
        tg_id = int(tg_id_str)
        if action == 'remove':
            await database.delete_user_data(db_pool, tg_id)
        elif action == 'block':
            user = await database.get_user(db_pool, tg_id)
            if user:
                new_status = not user['is_blocked']
                await database.update_user_status(db_pool, tg_id, new_status)
                
    await state.update_data(pending_actions={})
    await cq.message.edit_text("Submitted✅")

@dp.callback_query(F.data == "reg_change_pass")
async def change_pass_prompt(cq: types.CallbackQuery, state: FSMContext):
    current_pass = await database.get_mod_password(db_pool)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back", callback_data="reg_back"),
         InlineKeyboardButton(text="Cancel", callback_data="reg_cancel")]
    ])
    await cq.message.edit_text(f"Old Password: {current_pass}\nPlease Enter New Password:", reply_markup=kb)
    await state.set_state(AdminSettings.waiting_for_new_pass)

@dp.message(AdminSettings.waiting_for_new_pass)
async def save_new_password(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        await state.clear()
        await message.answer("Process Cancelled✅")
        return
    
    new_pass = message.text.strip()
    await database.update_mod_password(db_pool, new_pass)
    await state.clear()
    await message.answer(f"Password Changed✅\nYour New Password Is: {new_pass}")

# ---- ADMIN RESULTS & PUBLISH ----
@dp.message(F.text == "Result")
async def show_result_list(message: types.Message):
    results = await database.get_final_results(db_pool)
    if not results:
        return await message.answer("No results available yet.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{r['unique_id']} - {r['total_mark']}{'✅' if r['is_selected'] else '🔳'}", 
            callback_data=f"admin_toggle_{r['unique_id']}"
        )] for r in results
    ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="Submit", callback_data="admin_submit"),
        InlineKeyboardButton(text="Cancel", callback_data="admin_cancel")
    ])
    await message.answer("Final Results:\n", reply_markup=kb)

@dp.callback_query(F.data.startswith("admin_toggle_"))
async def toggle_result(cq: types.CallbackQuery):
    unique_id = cq.data.split("_")[2]
    await database.toggle_admin_selection(db_pool, unique_id)
    
    results = await database.get_final_results(db_pool)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{r['unique_id']} - {r['total_mark']}{'✅' if r['is_selected'] else '🔳'}", 
            callback_data=f"admin_toggle_{r['unique_id']}"
        )] for r in results
    ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="Submit", callback_data="admin_submit"),
        InlineKeyboardButton(text="Cancel", callback_data="admin_cancel")
    ])
    await cq.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data == "admin_submit")
async def submit_results_confirm(cq: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes✅", callback_data="admin_confirm_submit"), InlineKeyboardButton(text="No❌", callback_data="admin_reject_submit")]
    ])
    await cq.message.edit_text("Are you sure you want to submit?", reply_markup=kb)

@dp.callback_query(F.data == "admin_confirm_submit")
async def final_submit(cq: types.CallbackQuery):
    selected = await database.get_selected_members(db_pool)
    for user in selected:
        try:
            await bot.send_message(user['telegram_id'], "Congratulations! 🎊\n\nYou have been finally selected as a moderator for Team KBKh. All further instructions will be announced in the announcement.\n\n⚠️Don't tell anyone about the results!")
        except:
            pass
    await cq.message.edit_text("Submitted Successfully✅")

@dp.callback_query(F.data.in_({"admin_reject_submit", "admin_cancel"}))
async def cancel_admin_panel(cq: types.CallbackQuery):
    await cq.message.delete()
    if cq.data == "admin_reject_submit":
        await show_result_list(cq.message)

@dp.message(F.text == "Publish Result")
async def publish_results(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes✅", callback_data="pub_yes"), InlineKeyboardButton(text="No❌", callback_data="pub_no")]
    ])
    await message.answer("Are you sure you want to publish Result?", reply_markup=kb)

@dp.callback_query(F.data.startswith("pub_"))
async def execute_publish(cq: types.CallbackQuery):
    if cq.data == "pub_yes":
        marks = await database.get_all_members_marks(db_pool)
        for mark_data in marks:
            try:
                await bot.send_message(mark_data['telegram_id'], f"Your Obtained Mark: {mark_data['total_mark']}/25\n\nThank you for your participation♥️")
            except:
                pass
        await cq.message.edit_text("Results published successfully✅")
    else:
        await cq.message.delete()

# ================= RENDER WEB SERVER =================
async def handle_ping(request):
    return web.Response(text="Bot is running smoothly on Render!", status=200)

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

# ================= MAIN =================
async def main():
    global db_pool
    db_pool = await database.get_pool()
    
    await web_server()
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Webhook clear warning: {e}")
    
    print("Bot Started Successfully!")
    
    while True:
        try:
            await dp.start_polling(bot, direct_updates=True)
        except Exception as e:
            print(f"Polling error: {e}. Restarting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())

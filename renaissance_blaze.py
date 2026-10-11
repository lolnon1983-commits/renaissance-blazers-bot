import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

# RENAISSANCE BLAZE | BLACK RUSSIA
# Render Start Command: python renaissance_blaze.py
# Required Render environment variables: BOT_TOKEN, ADMIN_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("renaissance_blaze")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8798104630"))
FAMILY_NAME = "RENAISSANCE BLAZE"
MIN_STARS = 15
DATA_FILE = Path(os.getenv("DATA_FILE", "data.json"))


def empty_data():
    return {"users": {}, "applications": [], "withdrawals": [], "tasks": [], "shop": [], "orders": [],
            "next_application_id": 1, "next_withdrawal_id": 1, "next_task_id": 1,
            "next_shop_id": 1, "next_order_id": 1}


def load_data():
    if not DATA_FILE.exists():
        return empty_data()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        defaults = empty_data()
        for key, default in defaults.items():
            if key not in data or not isinstance(data[key], type(default)):
                data[key] = default
        return data
    except (OSError, json.JSONDecodeError) as exc:
        log.exception("Cannot read data file")
        raise RuntimeError("data.json is unreadable; inspect the file before restarting.") from exc


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=DATA_FILE.name, suffix=".tmp", dir=str(DATA_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, DATA_FILE)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def user_by_id(user_id):
    return load_data()["users"].get(str(user_id))


def register_user(tg_user, nickname=None):
    data = load_data()
    key = str(tg_user.id)
    user = data["users"].get(key)
    if user is None:
        user = {"id": tg_user.id, "username": tg_user.username or "", "nickname": (nickname or "").strip(),
                "balance": 0, "total_earned": 0, "total_approved_captures": 0,
                "registered_at": datetime.now().isoformat(timespec="seconds")}
        data["users"][key] = user
    else:
        user["username"] = tg_user.username or user.get("username", "")
        if nickname:
            user["nickname"] = nickname.strip()
    save_data(data)
    return user


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Мой баланс"), KeyboardButton(text="📋 Подать заявку")],
        [KeyboardButton(text="🎯 Задания"), KeyboardButton(text="🏆 Топ каптеров")],
        [KeyboardButton(text="🏪 Магазин"), KeyboardButton(text="💸 Вывод звёзд")],
        [KeyboardButton(text="📜 История заявок"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📖 Как зарабатывать"), KeyboardButton(text="🆘 Поддержка")],
    ], resize_keyboard=True)


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Заявки", callback_data="admin:apps"), InlineKeyboardButton(text="💸 Выводы", callback_data="admin:withdrawals")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🎯 Задания", callback_data="admin:tasks"), InlineKeyboardButton(text="🏪 Магазин", callback_data="admin:shop")],
    ])


def app_keyboard(app_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"app:approve:{app_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"app:reject:{app_id}"),
    ]])


def withdrawal_keyboard(wid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"wd:approve:{wid}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd:reject:{wid}"),
    ]])


class Register(StatesGroup): nickname = State()
class Apply(StatesGroup): nickname = State(); rank = State(); captures = State(); stars = State(); photos = State()
class Review(StatesGroup): captures = State(); stars = State()
class Rename(StatesGroup): nickname = State()
class Withdraw(StatesGroup): amount = State(); details = State()
class NewTask(StatesGroup): title = State(); description = State(); reward = State()
class NewItem(StatesGroup): title = State(); description = State(); price = State()
class Support(StatesGroup): message = State()

dp = Dispatcher(storage=MemoryStorage())


async def require_registration(message: Message):
    await message.answer("Сначала отправь свой игровой ник BLACK RUSSIA через /start.")


async def notify_application(bot: Bot, app):
    user = user_by_id(app["user_id"]) or {}
    caption = (f"📋 Заявка #{app['id']}\nНик: {app['nickname']}\nРанг: {app['rank']}\n"
               f"Заявлено каптов: {app['claimed_captures']}\nЗапрошено звёзд: {app['requested_stars']}\n"
               f"Telegram ID: {app['user_id']}")
    photos = app.get("screenshots", [])
    if photos:
        await bot.send_photo(ADMIN_ID, photos[0], caption=caption, reply_markup=app_keyboard(app["id"]))
        for photo in photos[1:]:
            await bot.send_photo(ADMIN_ID, photo)
    else:
        await bot.send_message(ADMIN_ID, caption + "\n⚠️ Скриншотов нет.", reply_markup=app_keyboard(app["id"]))


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = user_by_id(message.from_user.id)
    if not user or not user.get("nickname"):
        await state.set_state(Register.nickname)
        await message.answer(f"Добро пожаловать в {FAMILY_NAME}! 🔥\nОтправь свой игровой ник.")
        return
    register_user(message.from_user)
    await message.answer(f"С возвращением, {user['nickname']}!", reply_markup=menu())


@dp.message(Register.nickname)
async def finish_register(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    if nickname.lower() == "отмена":
        await state.clear(); await message.answer("Отменено. Для начала нажми /start."); return
    if not 2 <= len(nickname) <= 32:
        await message.answer("Ник должен быть длиной от 2 до 32 символов."); return
    register_user(message.from_user, nickname)
    await state.clear()
    await message.answer(f"Регистрация завершена, {nickname}! ✅", reply_markup=menu())


@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа к панели администратора."); return
    await message.answer(f"Панель администратора — {FAMILY_NAME}", reply_markup=admin_menu())
    await message.answer("Команды: /task_add, /shop_add, /balance TELEGRAM_ID СУММА, /broadcast ТЕКСТ")


@dp.message(Command("balance"))
async def admin_balance(message: Message):
    if not is_admin(message.from_user.id): return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Формат: /balance TELEGRAM_ID СУММА"); return
    try: target, amount = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть числами."); return
    data = load_data(); user = data["users"].get(str(target))
    if not user or int(user.get("balance", 0)) + amount < 0:
        await message.answer("Пользователь не найден или баланс не может стать отрицательным."); return
    user["balance"] = int(user.get("balance", 0)) + amount; save_data(data)
    await message.answer(f"Баланс пользователя {target} изменён на {amount} ⭐.")
    try: await message.bot.send_message(target, f"Администратор изменил твой баланс на {amount} ⭐.")
    except Exception: pass


@dp.message(Command("broadcast"))
async def broadcast(message: Message):
    if not is_admin(message.from_user.id): return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /broadcast текст"); return
    sent = failed = 0
    for uid in list(load_data()["users"]):
        try: await message.bot.send_message(int(uid), parts[1]); sent += 1
        except Exception: failed += 1
    await message.answer(f"Рассылка завершена. Отправлено: {sent}; ошибок: {failed}.")


@dp.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    data = load_data()
    await callback.message.answer(
        f"📊 Статистика\nИгроков: {len(data['users'])}\n"
        f"Заявок на проверку: {sum(a.get('status') == 'pending' for a in data['applications'])}\n"
        f"Заявок на вывод: {sum(w.get('status') == 'pending' for w in data['withdrawals'])}\n"
        f"Сумма балансов: {sum(int(u.get('balance', 0)) for u in data['users'].values())} ⭐")
    await callback.answer()


@dp.callback_query(F.data == "admin:apps")
async def admin_apps(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    pending = [a for a in load_data()["applications"] if a.get("status") == "pending"]
    if not pending: await callback.message.answer("Нет заявок на проверку.")
    else:
        for app in pending[:15]: await notify_application(callback.bot, app)
    await callback.answer()


@dp.callback_query(F.data.startswith("app:approve:"))
async def begin_review(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    app_id = int(callback.data.rsplit(":", 1)[1])
    app = next((a for a in load_data()["applications"] if a["id"] == app_id), None)
    if not app or app.get("status") != "pending": await callback.answer("Заявка уже обработана.", show_alert=True); return
    await state.set_state(Review.captures); await state.update_data(app_id=app_id)
    await callback.message.answer(f"Для заявки #{app_id} введи подтверждённое число каптов (0–{app['claimed_captures']}).")
    await callback.answer()


@dp.message(Review.captures)
async def review_captures(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    try: captures = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число."); return
    info = await state.get_data(); data = load_data()
    app = next((a for a in data["applications"] if a["id"] == info["app_id"]), None)
    if not app or app.get("status") != "pending": await state.clear(); await message.answer("Заявка не найдена или уже обработана."); return
    if captures < 0 or captures > int(app["claimed_captures"]): await message.answer("Число должно быть от 0 до заявленного количества."); return
    await state.update_data(captures=captures); await state.set_state(Review.stars)
    await message.answer("Введи количество начисляемых звёзд (0 или больше).")


@dp.message(Review.stars)
async def review_stars(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    try: stars = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число."); return
    if stars < 0: await message.answer("Звёзды не могут быть отрицательными."); return
    info = await state.get_data(); data = load_data()
    app = next((a for a in data["applications"] if a["id"] == info["app_id"]), None)
    if not app or app.get("status") != "pending": await state.clear(); await message.answer("Заявка не найдена или уже обработана."); return
    user = data["users"].get(str(app["user_id"]))
    if not user: await state.clear(); await message.answer("Пользователь не найден."); return
    captures = int(info["captures"])
    user["balance"] = int(user.get("balance", 0)) + stars
    user["total_earned"] = int(user.get("total_earned", 0)) + stars
    user["total_approved_captures"] = int(user.get("total_approved_captures", 0)) + captures
    app.update(status="approved", confirmed_captures=captures, awarded_stars=stars,
               reviewed_at=datetime.now().isoformat(timespec="seconds"), reviewed_by=message.from_user.id)
    save_data(data); await state.clear()
    await message.answer(f"Заявка #{app['id']} одобрена: {captures} каптов, {stars} ⭐.")
    try: await message.bot.send_message(int(app["user_id"]), f"✅ Заявка #{app['id']} одобрена. Подтверждено каптов: {captures}. Начислено: {stars} ⭐.")
    except Exception: pass


@dp.callback_query(F.data.startswith("app:reject:"))
async def reject_app(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    app_id = int(callback.data.rsplit(":", 1)[1]); data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app or app.get("status") != "pending": await callback.answer("Заявка уже обработана.", show_alert=True); return
    app.update(status="rejected", confirmed_captures=0, awarded_stars=0,
               reviewed_at=datetime.now().isoformat(timespec="seconds"), reviewed_by=callback.from_user.id)
    save_data(data)
    try: await callback.bot.send_message(int(app["user_id"]), f"❌ Заявка #{app_id} отклонена.")
    except Exception: pass
    await callback.message.answer(f"Заявка #{app_id} отклонена."); await callback.answer("Отклонено")


@dp.message(F.text == "📋 Подать заявку")
async def apply_start(message: Message, state: FSMContext):
    user = user_by_id(message.from_user.id)
    if not user or not user.get("nickname"): await require_registration(message); return
    await state.clear(); await state.set_state(Apply.nickname); await message.answer("Введи игровой ник, с которого выполнялся капт.")


@dp.message(Apply.nickname)
async def apply_nickname(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not 2 <= len(value) <= 32: await message.answer("Ник должен быть длиной 2–32 символа."); return
    await state.update_data(nickname=value); await state.set_state(Apply.rank); await message.answer("Введи свой ранг в семье.")


@dp.message(Apply.rank)
async def apply_rank(message: Message, state: FSMContext):
    value = (message.text or "").strip()
    if not value or len(value) > 60: await message.answer("Введи корректный ранг."); return
    await state.update_data(rank=value); await state.set_state(Apply.captures); await message.answer("Сколько каптов заявляешь? Введи число.")


@dp.message(Apply.captures)
async def apply_captures(message: Message, state: FSMContext):
    try: value = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число от 0 до 10000."); return
    if not 0 <= value <= 10000: await message.answer("Введи число от 0 до 10000."); return
    await state.update_data(claimed_captures=value); await state.set_state(Apply.stars); await message.answer(f"Сколько звёзд запрашиваешь? Минимум {MIN_STARS}.")


@dp.message(Apply.stars)
async def apply_stars(message: Message, state: FSMContext):
    try: value = int((message.text or "").strip())
    except ValueError: await message.answer(f"Введи целое число от {MIN_STARS} до 1000000."); return
    if not MIN_STARS <= value <= 1000000: await message.answer(f"Введи число от {MIN_STARS} до 1000000."); return
    await state.update_data(requested_stars=value, screenshots=[]); await state.set_state(Apply.photos)
    await message.answer("Отправь скриншоты фотографиями (до 20), затем напиши ГОТОВО.")


@dp.message(Apply.photos, F.photo)
async def apply_photo(message: Message, state: FSMContext):
    info = await state.get_data(); photos = info.get("screenshots", [])
    if len(photos) >= 20: await message.answer("Лимит 20 фото. Напиши ГОТОВО."); return
    photos.append(message.photo[-1].file_id); await state.update_data(screenshots=photos)
    await message.answer(f"Фото добавлено: {len(photos)}/20. Ещё фото или ГОТОВО.")


@dp.message(Apply.photos)
async def apply_finish(message: Message, state: FSMContext):
    if (message.text or "").strip().upper() != "ГОТОВО": await message.answer("Отправь фото или напиши ГОТОВО."); return
    info = await state.get_data(); photos = info.get("screenshots", [])
    if not photos: await message.answer("Нужен хотя бы один скриншот."); return
    data = load_data(); app_id = data["next_application_id"]; data["next_application_id"] += 1
    app = {"id": app_id, "user_id": message.from_user.id, "nickname": info["nickname"], "rank": info["rank"],
           "claimed_captures": info["claimed_captures"], "requested_stars": info["requested_stars"],
           "screenshots": photos, "status": "pending", "created_at": datetime.now().isoformat(timespec="seconds")}
    data["applications"].append(app); save_data(data); await state.clear()
    await message.answer(f"Заявка #{app_id} отправлена администратору. ✅", reply_markup=menu())
    try: await notify_application(message.bot, app)
    except Exception: log.exception("Could not notify admin for application %s", app_id)


@dp.message(F.text == "📜 История заявок")
async def history(message: Message):
    data = load_data(); apps = [a for a in data["applications"] if int(a["user_id"]) == message.from_user.id]
    if not apps: await message.answer("У тебя пока нет заявок."); return
    lines = ["📜 Твои последние заявки:"]
    for a in sorted(apps, key=lambda x: x["id"], reverse=True)[:15]:
        lines.append(f"#{a['id']} — {a['status']} | капты: {a.get('confirmed_captures', 'ожидают')} | ⭐ {a.get('awarded_stars', 0)}")
    await message.answer("\n".join(lines))


def rating_text(period):
    now = datetime.now(); start = None
    if period == "day": start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0); start = midnight - timedelta(days=midnight.weekday())
    elif period == "month": start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    data = load_data(); totals = {}
    for a in data["applications"]:
        if a.get("status") != "approved": continue
        if start:
            try: reviewed = datetime.fromisoformat(a.get("reviewed_at", ""))
            except ValueError: continue
            if reviewed < start: continue
        uid = str(a["user_id"]); totals[uid] = totals.get(uid, 0) + int(a.get("confirmed_captures", 0))
    rows = sorted([(data["users"].get(uid, {}).get("nickname", "Неизвестно"), n) for uid, n in totals.items()], key=lambda x: x[1], reverse=True)
    title = {"day": "за сегодня", "week": "за неделю", "month": "за месяц", "all": "за всё время"}.get(period, "за всё время")
    lines = [f"🏆 Топ каптеров {title}"]
    lines += [f"{i}. {name} — {n} каптов" for i, (name, n) in enumerate(rows[:10], 1)] or ["Пока нет подтверждённых каптов."]
    return "\n".join(lines)


@dp.message(F.text == "🏆 Топ каптеров")
async def leaderboard(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="День", callback_data="rating:day"), InlineKeyboardButton(text="Неделя", callback_data="rating:week")],
        [InlineKeyboardButton(text="Месяц", callback_data="rating:month"), InlineKeyboardButton(text="Всё время", callback_data="rating:all")]])
    await message.answer(rating_text("all"), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("rating:"))
async def rating_period(callback: CallbackQuery):
    period = callback.data.split(":", 1)[1]
    if period not in {"day", "week", "month", "all"}: await callback.answer("Неизвестный период", show_alert=True); return
    await callback.message.answer(rating_text(period)); await callback.answer()


@dp.message(F.text == "💰 Мой баланс")
async def balance(message: Message):
    user = user_by_id(message.from_user.id)
    if not user: await require_registration(message); return
    await message.answer(f"💰 Твой баланс: {int(user.get('balance', 0))} ⭐")


@dp.message(F.text == "👤 Мой профиль")
async def profile(message: Message):
    user = user_by_id(message.from_user.id)
    if not user: await require_registration(message); return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Изменить ник", callback_data="profile:rename")]])
    await message.answer(f"👤 Профиль\nНик: {user.get('nickname', '-')}\nБаланс: {user.get('balance', 0)} ⭐\n"
                         f"Подтверждённые капты: {user.get('total_approved_captures', 0)}\nЗаработано: {user.get('total_earned', 0)} ⭐\n"
                         f"Регистрация: {user.get('registered_at', '-')}", reply_markup=kb)


@dp.callback_query(F.data == "profile:rename")
async def rename_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Rename.nickname); await callback.message.answer("Отправь новый игровой ник (2–32 символа)."); await callback.answer()


@dp.message(Rename.nickname)
async def rename_finish(message: Message, state: FSMContext):
    nickname = (message.text or "").strip()
    if not 2 <= len(nickname) <= 32: await message.answer("Ник должен быть длиной 2–32 символа."); return
    data = load_data(); user = data["users"].get(str(message.from_user.id))
    if not user: await state.clear(); await message.answer("Сначала зарегистрируйся через /start."); return
    user["nickname"] = nickname; save_data(data); await state.clear(); await message.answer("Ник изменён. ✅", reply_markup=menu())


@dp.message(F.text == "🎯 Задания")
async def tasks_list(message: Message):
    tasks = [t for t in load_data()["tasks"] if t.get("active", True)]
    await message.answer("\n\n".join(f"#{t['id']} — {t['title']}\n{t['description']}\nНаграда: {t['reward']} ⭐" for t in tasks[:20]) if tasks else "Активных заданий пока нет.")


@dp.message(Command("task_add"))
async def task_add_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(NewTask.title); await message.answer("Введи название задания.")


@dp.message(NewTask.title)
async def task_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    title = (message.text or "").strip()
    if not title: await message.answer("Название не может быть пустым."); return
    await state.update_data(title=title[:100]); await state.set_state(NewTask.description); await message.answer("Введи описание.")


@dp.message(NewTask.description)
async def task_description(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    desc = (message.text or "").strip()
    if not desc: await message.answer("Описание не может быть пустым."); return
    await state.update_data(description=desc[:1000]); await state.set_state(NewTask.reward); await message.answer("Введи награду целым числом (0 или больше).")


@dp.message(NewTask.reward)
async def task_reward(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    try: reward = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число."); return
    if not 0 <= reward <= 1000000: await message.answer("Награда должна быть от 0 до 1000000."); return
    info = await state.get_data(); data = load_data(); tid = data["next_task_id"]; data["next_task_id"] += 1
    data["tasks"].append({"id": tid, "title": info["title"], "description": info["description"], "reward": reward, "active": True})
    save_data(data); await state.clear(); await message.answer(f"Задание #{tid} добавлено.")


@dp.callback_query(F.data == "admin:tasks")
async def admin_tasks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    tasks = [t for t in load_data()["tasks"] if t.get("active", True)]
    await callback.message.answer("\n".join(f"#{t['id']} {t['title']} — {t['reward']} ⭐" for t in tasks) if tasks else "Заданий нет. Добавь через /task_add.")
    await callback.answer()


@dp.message(F.text == "🏪 Магазин")
async def shop_list(message: Message):
    items = [i for i in load_data()["shop"] if i.get("active", True)]
    if not items: await message.answer("Магазин пока пуст."); return
    for item in items[:20]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"Купить за {item['price']} ⭐", callback_data=f"shop:buy:{item['id']}")]])
        await message.answer(f"🏪 {item['title']}\n{item['description']}\nЦена: {item['price']} ⭐", reply_markup=kb)


@dp.message(Command("shop_add"))
async def shop_add_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.set_state(NewItem.title); await message.answer("Введи название товара.")


@dp.message(NewItem.title)
async def item_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    title = (message.text or "").strip()
    if not title: await message.answer("Название не может быть пустым."); return
    await state.update_data(title=title[:100]); await state.set_state(NewItem.description); await message.answer("Введи описание товара.")


@dp.message(NewItem.description)
async def item_description(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    desc = (message.text or "").strip()
    if not desc: await message.answer("Описание не может быть пустым."); return
    await state.update_data(description=desc[:1000]); await state.set_state(NewItem.price); await message.answer("Введи цену целым числом больше нуля.")


@dp.message(NewItem.price)
async def item_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): await state.clear(); return
    try: price = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число."); return
    if not 1 <= price <= 1000000: await message.answer("Цена должна быть от 1 до 1000000."); return
    info = await state.get_data(); data = load_data(); iid = data["next_shop_id"]; data["next_shop_id"] += 1
    data["shop"].append({"id": iid, "title": info["title"], "description": info["description"], "price": price, "active": True})
    save_data(data); await state.clear(); await message.answer(f"Товар #{iid} добавлен.")


@dp.callback_query(F.data == "admin:shop")
async def admin_shop(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    items = [i for i in load_data()["shop"] if i.get("active", True)]
    await callback.message.answer("\n".join(f"#{i['id']} {i['title']} — {i['price']} ⭐" for i in items) if items else "Магазин пуст. Добавь через /shop_add.")
    await callback.answer()


@dp.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(callback: CallbackQuery):
    data = load_data(); user = data["users"].get(str(callback.from_user.id)); iid = int(callback.data.rsplit(":", 1)[1])
    item = next((i for i in data["shop"] if i["id"] == iid and i.get("active", True)), None)
    if not user or not item: await callback.answer("Пользователь или товар не найден.", show_alert=True); return
    price = int(item["price"])
    if int(user.get("balance", 0)) < price: await callback.answer("Недостаточно звёзд.", show_alert=True); return
    user["balance"] = int(user.get("balance", 0)) - price; oid = data["next_order_id"]; data["next_order_id"] += 1
    data["orders"].append({"id": oid, "user_id": callback.from_user.id, "item_id": iid, "title": item["title"], "price": price, "status": "pending"})
    save_data(data); await callback.message.answer(f"Заказ #{oid} оформлен. Администратор свяжется с тобой для выдачи товара.")
    try: await callback.bot.send_message(ADMIN_ID, f"🛒 Заказ #{oid}\nИгрок: {user.get('nickname', '-')}\nТовар: {item['title']}\nЦена: {price} ⭐\nID: {callback.from_user.id}")
    except Exception: log.exception("Cannot notify admin about shop order")
    await callback.answer("Заказ создан.")


@dp.message(F.text == "💸 Вывод звёзд")
async def withdraw_start(message: Message, state: FSMContext):
    user = user_by_id(message.from_user.id)
    if not user: await require_registration(message); return
    data = load_data()
    if any(int(w["user_id"]) == message.from_user.id and w.get("status") == "pending" for w in data["withdrawals"]):
        await message.answer("У тебя уже есть заявка на вывод на рассмотрении."); return
    await state.set_state(Withdraw.amount); await message.answer(f"Сколько звёзд вывести? Минимум {MIN_STARS}. Баланс: {user.get('balance', 0)} ⭐")


@dp.message(Withdraw.amount)
async def withdraw_amount(message: Message, state: FSMContext):
    try: amount = int((message.text or "").strip())
    except ValueError: await message.answer("Введи целое число."); return
    user = user_by_id(message.from_user.id)
    if amount < MIN_STARS or not user or amount > int(user.get("balance", 0)):
        await message.answer(f"Сумма должна быть не меньше {MIN_STARS} и не превышать твой баланс."); return
    await state.update_data(amount=amount); await state.set_state(Withdraw.details)
    await message.answer("Укажи способ связи или реквизиты для выплаты. Не отправляй пароли и коды входа.")


@dp.message(Withdraw.details)
async def withdraw_details(message: Message, state: FSMContext):
    details = (message.text or "").strip()
    if not 3 <= len(details) <= 500: await message.answer("Укажи текст длиной 3–500 символов."); return
    info = await state.get_data(); data = load_data(); user = data["users"].get(str(message.from_user.id)); amount = int(info["amount"])
    if not user or amount > int(user.get("balance", 0)): await state.clear(); await message.answer("Баланс изменился. Начни заявку заново."); return
    wid = data["next_withdrawal_id"]; data["next_withdrawal_id"] += 1
    wd = {"id": wid, "user_id": message.from_user.id, "amount": amount, "details": details, "status": "pending", "created_at": datetime.now().isoformat(timespec="seconds")}
    data["withdrawals"].append(wd); save_data(data); await state.clear()
    await message.answer(f"Заявка на вывод #{wid} отправлена. Выплата выполняется вручную после проверки.", reply_markup=menu())
    try: await message.bot.send_message(ADMIN_ID, f"💸 Вывод #{wid}\nИгрок: {user.get('nickname', '-')}\nСумма: {amount} ⭐\nСпособ/реквизиты: {details}\nID: {message.from_user.id}", reply_markup=withdrawal_keyboard(wid))
    except Exception: log.exception("Cannot notify admin about withdrawal")


@dp.callback_query(F.data == "admin:withdrawals")
async def admin_withdrawals(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    pending = [w for w in load_data()["withdrawals"] if w.get("status") == "pending"]
    if not pending: await callback.message.answer("Нет заявок на вывод.")
    else:
        for w in pending[:15]:
            await callback.message.answer(f"💸 Вывод #{w['id']}\nID: {w['user_id']}\nСумма: {w['amount']} ⭐\nРеквизиты: {w['details']}", reply_markup=withdrawal_keyboard(w['id']))
    await callback.answer()


@dp.callback_query(F.data.startswith("wd:approve:"))
async def wd_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    wid = int(callback.data.rsplit(":", 1)[1]); data = load_data(); wd = next((w for w in data["withdrawals"] if w["id"] == wid), None)
    if not wd or wd.get("status") != "pending": await callback.answer("Заявка уже обработана.", show_alert=True); return
    user = data["users"].get(str(wd["user_id"])); amount = int(wd["amount"])
    if not user or int(user.get("balance", 0)) < amount: await callback.answer("Недостаточно средств для списания.", show_alert=True); return
    user["balance"] = int(user.get("balance", 0)) - amount; wd.update(status="approved", reviewed_at=datetime.now().isoformat(timespec="seconds"), reviewed_by=callback.from_user.id); save_data(data)
    try: await callback.bot.send_message(int(wd["user_id"]), f"Заявка на вывод #{wid} одобрена на {amount} ⭐. Фактическую выплату администратор выполняет отдельно.")
    except Exception: pass
    await callback.message.answer(f"Вывод #{wid} одобрен. Не забудь провести фактическую выплату отдельно."); await callback.answer("Одобрено")


@dp.callback_query(F.data.startswith("wd:reject:"))
async def wd_reject(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    wid = int(callback.data.rsplit(":", 1)[1]); data = load_data(); wd = next((w for w in data["withdrawals"] if w["id"] == wid), None)
    if not wd or wd.get("status") != "pending": await callback.answer("Заявка уже обработана.", show_alert=True); return
    wd.update(status="rejected", reviewed_at=datetime.now().isoformat(timespec="seconds"), reviewed_by=callback.from_user.id); save_data(data)
    try: await callback.bot.send_message(int(wd["user_id"]), f"Заявка на вывод #{wid} отклонена. Баланс не списывался.")
    except Exception: pass
    await callback.message.answer(f"Вывод #{wid} отклонён."); await callback.answer("Отклонено")


@dp.message(F.text == "📖 Как зарабатывать")
async def guide(message: Message):
    await message.answer("📖 Как зарабатывать\n1. Выполняй капты и делай скриншоты.\n2. Нажми «📋 Подать заявку» и отправь данные со скриншотами.\n3. Дождись проверки. В рейтинг попадают только подтверждённые капты.\n4. Звёзды на балансе — внутренний учёт; выплаты и выдача товаров выполняются вручную администратором.")


@dp.message(F.text == "🆘 Поддержка")
async def support_start(message: Message, state: FSMContext):
    await state.set_state(Support.message); await message.answer("Напиши сообщение в поддержку. Не отправляй пароли или коды входа. Для отмены напиши ОТМЕНА.")


@dp.message(Support.message)
async def support_send(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "отмена": await state.clear(); await message.answer("Отменено.", reply_markup=menu()); return
    user = user_by_id(message.from_user.id) or {}; await state.clear()
    await message.answer("Сообщение отправлено администратору. ✅", reply_markup=menu())
    try:
        await message.bot.send_message(ADMIN_ID, f"🆘 Поддержка\nИгрок: {user.get('nickname', '-')}\nID: {message.from_user.id}\n\n{message.text or '[не текстовое сообщение]'}")
        if message.photo: await message.bot.send_photo(ADMIN_ID, message.photo[-1].file_id)
        elif message.document: await message.bot.send_document(ADMIN_ID, message.document.file_id)
    except Exception: log.exception("Cannot forward support message")


@dp.message()
async def fallback(message: Message):
    user = user_by_id(message.from_user.id)
    if not user or not user.get("nickname"):
        await message.answer("Для начала регистрации нажми /start.")
    elif message.text:
        await message.answer("Не понял сообщение. Используй кнопки меню или /start.", reply_markup=menu())


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it in Render Environment Variables.")
    if ADMIN_ID <= 0:
        raise RuntimeError("ADMIN_ID must be a positive Telegram numeric ID.")
    if not DATA_FILE.exists(): save_data(empty_data())
    else: load_data()
    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        log.info("Connected to Telegram as @%s", me.username)
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("Starting long polling for %s", FAMILY_NAME)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped")

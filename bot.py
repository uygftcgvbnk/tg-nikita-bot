import aiohttp.web
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatMemberStatus
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BOT_TOKEN = "8612249440:AAGoXZ_omSxVLBhKhxshKIwLGiOsQkwWCzQ"
ADMIN_IDS = [8210263644, 7828277438]
CONTACT_USER = "@D6net"

REQUIRED_CHANNELS = [
    {"title": "BlockFortres", "username": "BlockFortres", "url": "https://t.me/BlockFortres"},
    {"title": "ddnetrul34", "username": "ddnetrul34", "url": "https://t.me/ddnetrul34"},
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")

INITIAL_ARTS = {
    "cute": {
        "title": "Милый",
        "stars": 25,
        "image": os.path.join(BASE_DIR, "media_1792578748835_98d58b72.png"),
        "description": "",
    },
    "bust_mono": {
        "title": "Сисястый с однотонным фоном",
        "stars": 75,
        "image": os.path.join(BASE_DIR, "media_1792578747339_b0b59663.png"),
        "description": "",
    },
    "bust_bg": {
        "title": "Сисястый с фоном",
        "stars": 100,
        "image": os.path.join(BASE_DIR, "media_1792578745788_77a5fb37.png"),
        "description": "",
    },
    "bunny": {
        "title": "Любимый Никита",
        "stars": 100,
        "image": os.path.join(BASE_DIR, "media_1792578743814_8e3c2349.png"),
        "description": "",
    },
}

DEFAULT_DATA = {
    "promos": {
        "NIKITA10": {
            "percent": 10,
            "max_uses": 100,
            "used_count": 0,
            "expires_at": None,
            "duration_desc": "бессрочно",
            "used_by": [],
        }
    },
    "user_discounts": {},
    "stats": {
        "total_sales_count": 0,
        "total_stars_earned": 0,
        "orders": [],
    },
    "catalog": INITIAL_ARTS,
}


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA.copy()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "catalog" not in data or not data["catalog"]:
                data["catalog"] = INITIAL_ARTS.copy()
            # Миграция промокодов
            for code, val in list(data.get("promos", {}).items()):
                if isinstance(val, int):
                    data["promos"][code] = {
                        "percent": val,
                        "max_uses": 9999,
                        "used_count": 0,
                        "expires_at": None,
                        "duration_desc": "бессрочно",
                        "used_by": [],
                    }
            return data
    except Exception as e:
        logging.error(f"Error loading data.json: {e}")
        return DEFAULT_DATA.copy()


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving data.json: {e}")


logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class PromoStates(StatesGroup):
    entering_promo = State()


class AdminStates(StatesGroup):
    entering_promo_code = State()
    entering_promo_percent = State()
    entering_promo_max_uses = State()
    entering_promo_duration = State()

    # Добавление арта
    entering_art_title = State()
    entering_art_price = State()
    entering_art_description = State()
    entering_art_photo = State()


async def check_user_subscriptions(user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=f"@{ch['username']}", user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                return False
        except Exception as e:
            logging.error(f"Error checking subscription for {ch['username']}: {e}")
            return False
    return True


def get_sub_inline() -> InlineKeyboardMarkup:
    kb = []
    for ch in REQUIRED_CHANNELS:
        kb.append([InlineKeyboardButton(text=f"📢 Подписаться: {ch['title']}", url=ch["url"])])
    kb.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🛒 Купить арт"), KeyboardButton(text="🎨 Примеры артов")],
        [KeyboardButton(text="🎁 Промокод")],
    ]
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton(text="👑 Панель владельца")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_user_discount(user_id: int) -> int:
    data = load_data()
    return data.get("user_discounts", {}).get(str(user_id), 0)


def calculate_discounted_price(base_stars: int, discount_pct: int) -> int:
    if discount_pct <= 0:
        return base_stars
    discounted = int(round(base_stars * (100 - discount_pct) / 100))
    return max(1, discounted)


def get_catalog_inline(user_id: int) -> InlineKeyboardMarkup:
    data = load_data()
    catalog = data.get("catalog", INITIAL_ARTS)
    discount = get_user_discount(user_id)
    buttons = []
    for art_key, item in catalog.items():
        price = calculate_discounted_price(item["stars"], discount)
        if discount > 0:
            price_text = f"⭐ {price} (скидка {discount}%, было {item['stars']}⭐)"
        else:
            price_text = f"⭐ {price} звёзд"
        text = f"{item['title']} — {price_text}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"view_{art_key}")])

    # Добавляем пункт «Что-то своё - цена????»
    buttons.append([InlineKeyboardButton(text="✨ Что-то своё — цена????", callback_data="custom_order")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    await state.clear()
    is_subscribed = await check_user_subscriptions(message.from_user.id)

    if not is_subscribed:
        text = (
            f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
            "⚠️ <b>Для доступа к боту и заказам артов необходимо подписаться на наши каналы:</b>\n"
            "1. <a href='https://t.me/BlockFortres'>BlockFortres</a>\n"
            "2. <a href='https://t.me/ddnetrul34'>ddnetrul34</a>\n\n"
            "После подписки на оба канала нажмите кнопку <b>«✅ Я подписался»</b> ниже."
        )
        await message.answer(text, reply_markup=get_sub_inline(), parse_mode="HTML")
        return

    discount = get_user_discount(message.from_user.id)
    discount_msg = f"\n🔥 Ваша активная скидка: <b>{discount}%</b>" if discount > 0 else ""

    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "Добро пожаловать в арт-мастерскую по <b>DDNet</b>!{discount_msg}\n\n"
        "Здесь ты можешь посмотреть примеры артов и купить любой арт за <b>Telegram Stars (Звёзды)</b> ⭐\n\n"
        "👇 <b>Выбери нужный раздел:</b>"
    ).format(discount_msg=discount_msg)

    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "check_subscription")
async def handle_check_sub(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    is_subscribed = await check_user_subscriptions(user_id)

    if not is_subscribed:
        await callback.answer(
            "❌ Вы не подписались на все обязательные каналы! Подпишитесь на оба канала и попробуйте снова.",
            show_alert=True,
        )
        return

    await callback.message.delete()
    discount = get_user_discount(user_id)
    discount_msg = f"\n🔥 Ваша активная скидка: <b>{discount}%</b>" if discount > 0 else ""
    await callback.message.answer(
        f"✅ <b>Спасибо за подписку!</b>{discount_msg}\n\nДобро пожаловать в магазин артов DDNet!",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="HTML",
    )


@dp.message(F.text == "🛒 Купить арт")
async def handle_catalog(message: types.Message):
    is_sub = await check_user_subscriptions(message.from_user.id)
    if not is_sub:
        await message.answer("⚠️ Сначала подпишитесь на каналы:", reply_markup=get_sub_inline())
        return

    discount = get_user_discount(message.from_user.id)
    disc_text = f"\n🎁 Применена скидка по промокоду: <b>{discount}%</b>" if discount > 0 else ""

    text = (
        f"🎨 <b>Прайс-лист и каталог артов DDNet</b>{disc_text}\n\n"
        "Выберите понравившийся арт, чтобы посмотреть его и оформить покупку за ⭐ Звёзды:"
    )
    await message.answer(text, reply_markup=get_catalog_inline(message.from_user.id), parse_mode="HTML")


@dp.message(F.text == "🎨 Примеры артов")
async def handle_examples(message: types.Message):
    is_sub = await check_user_subscriptions(message.from_user.id)
    if not is_sub:
        await message.answer("⚠️ Сначала подпишитесь на каналы:", reply_markup=get_sub_inline())
        return

    discount = get_user_discount(message.from_user.id)
    data = load_data()
    catalog = data.get("catalog", INITIAL_ARTS)

    await message.answer("🖼 <b>Прайс-лист артов:</b>", parse_mode="HTML")

    for art_key, item in catalog.items():
        price = calculate_discounted_price(item["stars"], discount)
        if discount > 0:
            price_line = f"{price} Звёзд (скидка {discount}%, было {item['stars']}⭐)"
        else:
            price_line = f"{price} Звёзд"

        caption_parts = [
            "<b>Прайс лист никиты❤️</b>",
            item["title"],
            price_line,
        ]
        if item.get("description"):
            caption_parts.append(f"📝 {item['description']}")

        caption = "\n".join(caption_parts)

        buy_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"⭐ Купить за {price} звёзд", callback_data=f"buy_stars_{art_key}")]
            ]
        )

        img_path = item.get("image")
        file_id = item.get("file_id")

        if file_id:
            await message.answer_photo(photo=file_id, caption=caption, reply_markup=buy_markup, parse_mode="HTML")
        elif img_path and os.path.exists(img_path):
            photo = FSInputFile(img_path)
            await message.answer_photo(photo=photo, caption=caption, reply_markup=buy_markup, parse_mode="HTML")
        else:
            await message.answer(caption, reply_markup=buy_markup, parse_mode="HTML")


@dp.callback_query(F.data.startswith("view_"))
async def handle_view_art(callback: types.CallbackQuery):
    art_key = callback.data.replace("view_", "")
    data = load_data()
    catalog = data.get("catalog", INITIAL_ARTS)
    item = catalog.get(art_key)
    if not item:
        await callback.answer("Арт не найден.")
        return

    discount = get_user_discount(callback.from_user.id)
    price = calculate_discounted_price(item["stars"], discount)

    if discount > 0:
        price_caption = f"⭐ <b>{price} звёзд</b> <s>(было {item['stars']}⭐)</s> [Скидка {discount}%]"
    else:
        price_caption = f"⭐ <b>{price} звёзд</b>"

    caption_parts = [
        "<b>Прайс лист никиты❤️</b>",
        item["title"],
        f"Стоимость: <b>{price_caption}</b>",
    ]
    if item.get("description"):
        caption_parts.append(f"📝 {item['description']}")
    caption_parts.append("\nНажмите кнопку ниже для покупки звёздами:")

    caption = "\n".join(caption_parts)

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить ({price} звёзд)", callback_data=f"buy_stars_{art_key}")],
            [InlineKeyboardButton(text="◀️ Назад в каталог", callback_data="back_to_catalog")],
        ]
    )

    img_path = item.get("image")
    file_id = item.get("file_id")

    if file_id:
        await callback.message.delete()
        await callback.message.answer_photo(photo=file_id, caption=caption, reply_markup=markup, parse_mode="HTML")
    elif img_path and os.path.exists(img_path):
        photo = FSInputFile(img_path)
        await callback.message.delete()
        await callback.message.answer_photo(photo=photo, caption=caption, reply_markup=markup, parse_mode="HTML")
    else:
        await callback.message.edit_text(caption, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "custom_order")
async def handle_custom_order(callback: types.CallbackQuery):
    text = (
        "✨ <b>Индивидуальный заказ: «Что-то своё»</b>\n\n"
        "💰 <b>Цена:</b> договорная (зависит от сложности и деталей)\n\n"
        f"📩 Чтобы обсудить вашу идею, референсы и стоимость, напишите напрямую автору: {CONTACT_USER}"
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать автору @D6net", url="https://t.me/D6net")],
            [InlineKeyboardButton(text="◀️ Назад в каталог", callback_data="back_to_catalog")],
        ]
    )

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "back_to_catalog")
async def handle_back_catalog(callback: types.CallbackQuery):
    text = "🎨 <b>Каталог доступных артов по DDNet</b>\n\nВыберите нужный вариант:"
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=get_catalog_inline(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("buy_stars_"))
async def handle_buy_stars(callback: types.CallbackQuery):
    art_key = callback.data.replace("buy_stars_", "")
    data = load_data()
    catalog = data.get("catalog", INITIAL_ARTS)
    item = catalog.get(art_key)
    if not item:
        await callback.answer("Товар не найден", show_alert=True)
        return

    discount = get_user_discount(callback.from_user.id)
    price_stars = calculate_discounted_price(item["stars"], discount)

    prices = [LabeledPrice(label=item["title"], amount=price_stars)]

    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Заказ: {item['title']}",
            description=f"Покупка арта '{item['title']}'. После оплаты свяжитесь с {CONTACT_USER} для получения исходников.",
            payload=f"order_{art_key}_{callback.from_user.id}_{price_stars}",
            currency="XTR",
            prices=prices,
            provider_token="",
        )
        await callback.answer("Счёт на оплату выставлен выше!")
    except Exception as e:
        logging.error(f"Failed to send invoice: {e}")
        await callback.message.answer(
            f"💰 Для оплаты <b>{price_stars} ⭐ звёзд</b> перейдите к автору напрямую:\n"
            f"👉 {CONTACT_USER}\n\nУкажите: <i>«Хочу купить {item['title']} за {price_stars} звёзд»</i>",
            parse_mode="HTML",
        )
        await callback.answer()


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    payment_info = message.successful_payment
    stars_amount = payment_info.total_amount

    data = load_data()
    data["stats"]["total_sales_count"] += 1
    data["stats"]["total_stars_earned"] += stars_amount
    data["stats"]["orders"].append({
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "stars": stars_amount,
        "payload": payment_info.invoice_payload,
    })
    save_data(data)

    success_text = (
        "🎉 <b>Оплата успешно прошла!</b>\n\n"
        f"Вы оплатили <b>{stars_amount} ⭐ звёзд</b>!\n"
        f"📩 Напишите автору {CONTACT_USER}, чтобы отправить ТЗ или получить готовый арт."
    )
    await message.answer(success_text, parse_mode="HTML")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>НОВАЯ ПОКУПКА!</b>\n"
                f"Покупатель: @{message.from_user.username} (ID: {message.from_user.id})\n"
                f"Сумма: <b>{stars_amount} ⭐ звёзд</b>\n"
                f"Детали: <code>{payment_info.invoice_payload}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ---------------- РАЗДЕЛ ПРОМОКОДОВ ----------------
@dp.message(F.text == "🎁 Промокод")
async def handle_promo_menu(message: types.Message, state: FSMContext):
    is_sub = await check_user_subscriptions(message.from_user.id)
    if not is_sub:
        await message.answer("⚠️ Сначала подпишитесь на каналы:", reply_markup=get_sub_inline())
        return

    await message.answer("введите промокод")
    await state.set_state(PromoStates.entering_promo)


@dp.message(StateFilter(PromoStates.entering_promo))
async def handle_enter_promo(message: types.Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    data = load_data()
    user_id = message.from_user.id

    promo_info = data.get("promos", {}).get(promo_code)

    if not promo_info:
        await message.answer("❌ Неверный промокод! Попробуйте снова или отправьте /start для отмены.")
        return

    expires_at = promo_info.get("expires_at")
    if expires_at and time.time() > expires_at:
        await message.answer("⌛ Срок действия этого промокода истёк.")
        return

    max_uses = promo_info.get("max_uses", 9999)
    used_count = promo_info.get("used_count", 0)
    used_by = promo_info.get("used_by", [])

    if user_id in used_by:
        await message.answer("⚠️ Вы уже активировали этот промокод ранее!")
        await state.clear()
        return

    if used_count >= max_uses:
        await message.answer("🚫 Этот промокод исчерпал максимальное количество активаций.")
        return

    discount_pct = promo_info["percent"]
    promo_info["used_count"] = used_count + 1
    used_by.append(user_id)
    promo_info["used_by"] = used_by
    data["promos"][promo_code] = promo_info

    data["user_discounts"][str(user_id)] = discount_pct
    save_data(data)

    await state.clear()
    await message.answer(
        f"🎉 <b>Промокод {promo_code} успешно активирован!</b>\n"
        f"Вам начислена скидка <b>{discount_pct}%</b> на весь каталог артов! ⭐",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user_id),
    )


# ---------------- ПАНЕЛЬ ВЛАДЕЛЬЦА ----------------
def get_admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
            [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin_delete_promo_menu")],
            [InlineKeyboardButton(text="🎨 Добавить новый арт", callback_data="admin_add_art")],
            [InlineKeyboardButton(text="🗑 Удалить арт", callback_data="admin_delete_art_menu")],
            [InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_refresh_stats")],
        ]
    )


def format_admin_text(data) -> str:
    stats = data.get("stats", {})
    promos = data.get("promos", {})
    catalog = data.get("catalog", {})

    lines = []
    for code, p in promos.items():
        dur = p.get("duration_desc", "бессрочно")
        max_u = p.get("max_uses", "∞")
        used_u = p.get("used_count", 0)
        lines.append(f"• <code>{code}</code>: <b>{p['percent']}%</b> (исп: {used_u}/{max_u}, {dur})")
    promos_list = "\n".join(lines) if lines else "Нет активных промокодов"

    arts_lines = [f"• {item['title']} — ⭐ {item['stars']}" for item in catalog.values()]
    arts_list = "\n".join(arts_lines) if arts_lines else "Каталог пуст"

    return (
        "👑 <b>Панель управления владельца</b>\n\n"
        f"📊 <b>Статистика продаж:</b>\n"
        f"• Количество покупок: <b>{stats.get('total_sales_count', 0)}</b>\n"
        f"• Выручка: <b>{stats.get('total_stars_earned', 0)} ⭐ звёзд</b>\n\n"
        f"🎟 <b>Промокоды:</b>\n{promos_list}\n\n"
        f"🎨 <b>Арты в магазине:</b>\n{arts_list}"
    )


@dp.message(F.text == "👑 Панель владельца")
async def handle_admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этому разделу.")
        return
    await state.clear()
    data = load_data()
    await message.answer(format_admin_text(data), reply_markup=get_admin_main_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_refresh_stats")
async def handle_refresh_stats(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    data = load_data()
    await callback.message.edit_text(format_admin_text(data), reply_markup=get_admin_main_kb(), parse_mode="HTML")
    await callback.answer("Обновлено!")


# --- УДАЛЕНИЕ ПРОМОКОДОВ ---
@dp.callback_query(F.data == "admin_delete_promo_menu")
async def handle_delete_promo_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    data = load_data()
    promos = data.get("promos", {})
    if not promos:
        await callback.answer("Нет промокодов для удаления.", show_alert=True)
        return

    kb = []
    for code in promos.keys():
        kb.append([InlineKeyboardButton(text=f"❌ Удалить {code}", callback_data=f"del_promo_{code}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_refresh_stats")])

    await callback.message.edit_text("Выберите промокод, который хотите удалить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("del_promo_"))
async def handle_del_promo_action(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    code = callback.data.replace("del_promo_", "")
    data = load_data()
    if code in data.get("promos", {}):
        del data["promos"][code]
        save_data(data)
        await callback.answer(f"Промокод {code} удалён!", show_alert=True)
    await handle_delete_promo_menu(callback)


# --- СОЗДАНИЕ ПРОМОКОДА ---
@dp.callback_query(F.data == "admin_create_promo")
async def handle_start_create_promo(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.entering_promo_code)
    await callback.message.answer("✏️ Введите название нового промокода (например: <code>DDNET50</code>):", parse_mode="HTML")
    await callback.answer()


@dp.message(StateFilter(AdminStates.entering_promo_code))
async def handle_promo_code_input(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.update_data(new_promo_code=code)
    await state.set_state(AdminStates.entering_promo_percent)
    await message.answer(f"Промокод: <code>{code}</code>\nВведите процент скидки (число от 1 до 99):", parse_mode="HTML")


@dp.message(StateFilter(AdminStates.entering_promo_percent))
async def handle_promo_percent_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 99):
        await message.answer("❌ Введите корректное число процентов от 1 до 99:")
        return

    await state.update_data(new_promo_percent=int(text))
    await state.set_state(AdminStates.entering_promo_max_uses)
    await message.answer(
        "🔢 Введите лимит активаций (число, например: <code>10</code> или <code>100</code>):",
        parse_mode="HTML",
    )


@dp.message(StateFilter(AdminStates.entering_promo_max_uses))
async def handle_promo_max_uses_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Введите положительное число активаций (например: 10):")
        return

    await state.update_data(new_promo_max_uses=int(text))
    await state.set_state(AdminStates.entering_promo_duration)
    await message.answer(
        "⏳ Введите срок действия в днях (например: <code>1</code> для 1 дня, или <code>0</code> если бессрочно):",
        parse_mode="HTML",
    )


@dp.message(StateFilter(AdminStates.entering_promo_duration))
async def handle_promo_duration_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите количество дней числом (например: 1 или 0):")
        return

    days = int(text)
    user_data = await state.get_data()
    code = user_data["new_promo_code"]
    percent = user_data["new_promo_percent"]
    max_uses = user_data["new_promo_max_uses"]

    if days > 0:
        expires_at = time.time() + (days * 86400)
        dur_desc = f"{days} дн."
    else:
        expires_at = None
        dur_desc = "бессрочно"

    data = load_data()
    data["promos"][code] = {
        "percent": percent,
        "max_uses": max_uses,
        "used_count": 0,
        "expires_at": expires_at,
        "duration_desc": dur_desc,
        "used_by": [],
    }
    save_data(data)

    await state.clear()
    await message.answer(
        f"✅ <b>Промокод успешно создан!</b>\n\n"
        f"• Код: <code>{code}</code>\n"
        f"• Скидка: <b>{percent}%</b>\n"
        f"• Лимит: <b>{max_uses}</b>\n"
        f"• Срок: <b>{dur_desc}</b>",
        parse_mode="HTML",
    )


# --- ДОБАВЛЕНИЕ НОВОГО АРТА ---
@dp.callback_query(F.data == "admin_add_art")
async def handle_start_add_art(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.entering_art_title)
    await callback.message.answer("🎨 <b>Добавление арта (Шаг 1 из 4)</b>\nВведите название арта:", parse_mode="HTML")
    await callback.answer()


@dp.message(StateFilter(AdminStates.entering_art_title))
async def handle_art_title_input(message: types.Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(art_title=title)
    await state.set_state(AdminStates.entering_art_price)
    await message.answer(f"Название: <b>{title}</b>\n\n💰 <b>(Шаг 2 из 4)</b> Введите цену в ⭐ звёздах (целое число, например: <code>50</code>):", parse_mode="HTML")


@dp.message(StateFilter(AdminStates.entering_art_price))
async def handle_art_price_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Введите цену числом звёзд (например: 50):")
        return

    await state.update_data(art_price=int(text))
    await state.set_state(AdminStates.entering_art_description)
    await message.answer(
        "📝 <b>(Шаг 3 из 4)</b> Введите описание арта (или отправьте <code>-</code> / <code>пропустить</code>, если описание не нужно):",
        parse_mode="HTML",
    )


@dp.message(StateFilter(AdminStates.entering_art_description))
async def handle_art_desc_input(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    if desc.lower() in ["-", "пропустить", "нет"]:
        desc = ""
    await state.update_data(art_desc=desc)
    await state.set_state(AdminStates.entering_art_photo)
    await message.answer(
        "🖼 <b>(Шаг 4 из 4)</b> Отправьте фото (изображение) этого арта:",
        parse_mode="HTML",
    )


@dp.message(StateFilter(AdminStates.entering_art_photo), F.photo)
async def handle_art_photo_input(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    user_data = await state.get_data()

    art_id = f"art_{int(time.time())}"
    title = user_data["art_title"]
    price = user_data["art_price"]
    desc = user_data["art_desc"]

    data = load_data()
    data["catalog"][art_id] = {
        "title": title,
        "stars": price,
        "description": desc,
        "file_id": photo.file_id,
    }
    save_data(data)

    await state.clear()
    await message.answer(
        f"✅ <b>Арт успешно добавлен в каталог и примеры!</b>\n\n"
        f"🎨 <b>Название:</b> {title}\n"
        f"💰 <b>Цена:</b> ⭐ {price} звёзд\n"
        f"📝 <b>Описание:</b> {desc or 'нет'}",
        parse_mode="HTML",
    )


# --- УДАЛЕНИЕ АРТА ---
@dp.callback_query(F.data == "admin_delete_art_menu")
async def handle_delete_art_menu(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    data = load_data()
    catalog = data.get("catalog", {})
    if not catalog:
        await callback.answer("Каталог пуст.", show_alert=True)
        return

    kb = []
    for art_key, item in catalog.items():
        kb.append([InlineKeyboardButton(text=f"❌ {item['title']}", callback_data=f"del_art_{art_key}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_refresh_stats")])

    await callback.message.edit_text("Выберите арт, который хотите удалить из магазина:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("del_art_"))
async def handle_del_art_action(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    art_key = callback.data.replace("del_art_", "")
    data = load_data()
    if art_key in data.get("catalog", {}):
        title = data["catalog"][art_key]["title"]
        del data["catalog"][art_key]
        save_data(data)
        await callback.answer(f"Арт '{title}' удалён!", show_alert=True)
    await handle_delete_art_menu(callback)



async def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    app = aiohttp.web.Application()
    async def index(request):
        return aiohttp.web.Response(text="Bot is running!")
    app.router.add_get("/", index)
    app.router.add_get("/healthz", index)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health server started on port {port}")

async def main():
    print("Бот DDNet Art запущен...")
    await start_health_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

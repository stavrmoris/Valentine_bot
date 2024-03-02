import re
import asyncio
import logging
import sqlite3

from datetime import datetime, timedelta
from aiogram.enums import ContentType
from config_reader import config, PAYMENTS_TOKEN
from aiogram.types import Message
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest

connection = sqlite3.connect('data.db')
cursor = connection.cursor()


logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.bot_token.get_secret_value())
dp = Dispatcher()

PRICE = types.LabeledPrice(label="Подписка на 1 месяц", amount=169 * 100)  # в копейках (руб)
user_id = 0
user2 = 0
name = "неопределенно"
user_only = False
canWrite = False


def date_integer(dt_time):
    return 10000 * dt_time.year + 100 * dt_time.month + dt_time.day


@dp.callback_query(F.data == "buy")
async def buy(message: types.Message):
    if PAYMENTS_TOKEN.split(':')[1] == 'TEST':
        await message.answer("Тестовый платеж!!!")

    await bot.send_invoice(message.from_user.id,
                           title="Подписка на бота",
                           description="🤖 Активация подписки на бота на 30 дней",
                           provider_token=PAYMENTS_TOKEN,
                           currency="rub",
                           photo_url="https://www.aroged.com/wp-content/uploads/2022/06/Telegram-has-a-premium-subscription.jpg",
                           photo_width=416,
                           photo_height=234,
                           photo_size=416,
                           is_flexible=False,
                           prices=[PRICE],
                           start_parameter='fount-of-discounts',
                           payload="test-invoice-payload")


@dp.pre_checkout_query(lambda query: True)
async def pre_checkout_query(pre_checkout_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)


@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    print("SUCCESSFUL PAYMENT:")

    print(f"ID купившего премиум: {message.from_user.id}")
    cursor.execute('INSERT INTO Users (user, date) VALUES (?, ?)',
                   (f'{message.from_user.id}', date_integer(datetime.now() + timedelta(days=30))))
    connection.commit()

    payment_info = message.successful_payment.to_python()
    for k, v in payment_info.items():
        print(f"{k} = {v}")

    await bot.send_message(message.chat.id,
                           f"💵 Платеж на сумму {message.successful_payment.total_amount // 100} {message.successful_payment.currency} прошел успешно! Спасибо, что пользуетесь нашим сервисом 🥰 !!!")


@dp.message(CommandStart(deep_link=True, magic=F.args.regexp(re.compile(r'user_(\d+)'))))
async def cmd_start_book(message: Message, command: CommandObject):
    global user_id
    global canWrite
    global user2
    global name

    name = message.from_user.username
    user2 = message.from_user.id
    user_id = command.args.split("_")[1]
    await message.answer(f"✉️ Напишите ваше сообщение:")
    canWrite = True


@dp.message(CommandStart())
async def process_start_command(message: types.Message):
    link = f"t.me/stavrmoris_testbot?start=user_{str(message.from_user.id)}"

    message_buttons = [
        [
            types.InlineKeyboardButton(
                 text="🔗 Поделиться ссылкой",
                 switch_inline_query=f"\n💌 Напишите мне анонимную валентинку:\n\n{link}"
            )
        ],

        [
            types.InlineKeyboardButton(
                text="Анонимно написать пользователю",
                callback_data="message_username"
            )
        ]
    ]

    message_builder = types.InlineKeyboardMarkup(inline_keyboard=message_buttons)

    await message.answer(
        f"❤️ Твоя ссылка для признаний: {link}\n\n📌 Закрепи эту ссылку в профиле или поделись с друзьями, чтобы получать анонимные валентинки!",
        reply_markup=message_builder
    )


@dp.message(F.text)
async def any_message(message: Message):
    global canWrite
    global user_only
    global user_id

    if user_only:

        if message.forward_from is not None:
            user_id = message.forward_from.id
            print("user reply id: ", message.forward_from.id)
            await message.answer("🎉 Мы приняли никнейм! Теперь напишите сообщение.")
            canWrite = True
            user_only = False
        else:
            await message.answer(f"🤖 Простите, но пользователь заблокировал возможность распознавания ника по сообщениям.")


    elif canWrite:
        await message.answer("Ваше сообщение успешно отправлено!")
        buttons = [
            [types.InlineKeyboardButton(
                text="🥸 Анонимно ответить",
                callback_data=f"user_{str(message.from_user.id)}"
            )],
            [types.InlineKeyboardButton(
                text="🥷 Узнать отправителя",
                callback_data="premium"
            )]
        ]
        builder = types.InlineKeyboardMarkup(inline_keyboard=buttons)

        await bot.send_message(
            chat_id=user_id,
            text=f"💌 Вам отправили анонимное сообщение:\n\n{message.text}",
            reply_markup=builder
        )

        canWrite = False


@dp.callback_query(F.data == "message_username")
async def message_link(callback: types.CallbackQuery):
    global user_only

    user_only = True
    await callback.message.edit_text(text=f"👱 Отправьте любое сообщение пользователя, которому хотите написать.\nЛибо отправьте ник пользователя. Например: @people")
    await callback.answer()


@dp.callback_query(F.data.startswith("user_"))
async def callbacks_num(callback: types.CallbackQuery):
    global user_id
    global user2
    global canWrite
    global name

    name = callback.from_user.username
    user_id = callback.data.split("_")[1]
    user2 = callback.from_user.id
    canWrite = True
    await callback.message.edit_text("✉️ Напишите ваше сообщение:")

    await callback.answer()


@dp.callback_query(F.data == "premium")
async def send_random_value(callback: types.CallbackQuery):
    global user_id
    global name
    global user2

    cursor.execute("SELECT * FROM users WHERE user = ?", (user_id,))
    results = cursor.fetchone()

    print("user_id", user_id)
    print("user2", user2)
    print(name)
    print(results)

    if (results and user_id in results) and (results[1] and datetime.strptime(str(results[1]), '%Y%m%d') >= datetime.now()):
        user_name = f"👱 Кликните, чтобы узнать, кто вам написал.\n\n🎇 Это был пользователь с id: {user2} и ником: {name}\n\n\n"
        mention = "[" + user_name + "](t.me/" + str(name) + ")"
        await callback.message.answer(mention, parse_mode="Markdown")
    else:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(
            text="💵 Купить",
            callback_data="buy")
        )

        await callback.message.answer(
            f"💁 Чтобы узнать отправителя - купите 30 дневную подписку на бота, всего за 169 руб.",
            reply_markup=builder.as_markup()
        )
    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
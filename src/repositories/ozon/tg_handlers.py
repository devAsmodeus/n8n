import asyncio

from src.config import settings

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from src.repositories.ozon.format_message import edit_messages
from src.repositories.ozon.parser_products import get_product_name, get_product_data
from src.repositories.ozon.answer_messages import *


bot = Bot(token=settings.BOT_TOKEN)
router = Router()


class AwaitMessage(StatesGroup):
    message_state = State()
    sort_state = State()
    stars_state = State()
    comment_state = State()


@router.message(
    CommandStart()
)
async def first_run_handler(
        message: Message
) -> None:
    await message.delete()
    await message.answer(
        text=start_message
    )


@router.message(
    Command("searchitems")
)
async def search_items_handler(
        message: Message,
        state: FSMContext
) -> None:
    await state.clear()
    await message.delete()
    await message.answer(
        text=search_items,
        parse_mode='HTML'
    )
    await state.set_state(
        state=AwaitMessage.message_state
    )


@router.message(
    AwaitMessage.message_state,
    F.text.startswith("https://")
)
async def coefficient_chosen(
        message: Message,
        state: FSMContext
):
    await state.clear()
    product_url = message.text.strip()
    product_name, sku_id = await get_product_name(product_url)

    builder = InlineKeyboardBuilder()
    for sort_button, sort_callback in zip(
            ('Дешевые', 'Популярные', 'С высоким рейтингом', 'Новинки'),
            ('price', 'score', 'rating', 'new')
    ):
        builder.button(
            text=sort_button,
            callback_data=f'sort_{sort_callback}'
        )
    else:
        await state.set_state(AwaitMessage.sort_state)
        await state.update_data(
            product_url=product_url,
            product_name=product_name,
            sku_id=sku_id,
        )

        builder.adjust(1)
        await message.answer(
            text=search_answer.format(product_name=product_name),
            reply_markup=builder.as_markup()
        )

        asyncio.create_task(timeout_handler(
            user_id=message.from_user.id,
            state=state
        ))


async def timeout_handler(
        user_id: int,
        state: FSMContext,
):
    await asyncio.sleep(60 * 5)  # 5 минут
    current_state = await state.get_state()
    if current_state == AwaitMessage.sort_state.state:
        data = await state.get_data()
        product_url = data.get("product_url")
        product_name = data.get("product_name")
        sku_id = data.get("sku_id")
        await state.clear()

        product_data = await get_product_data(
            product_name=product_name,
            sorting_type='price',
        )
        await edit_messages(
            bot=bot,
            user_id=user_id,
            products=product_data,
        )
        await state.set_state(AwaitMessage.stars_state)
        asyncio.create_task(timeout_stars_handler(
            user_id=user_id,
            state=state
        ))


@router.callback_query(
    AwaitMessage.sort_state,
    F.data.startswith("sort_")
)
async def sort_type_handler(
        callback: CallbackQuery,
        state: FSMContext
) -> None:
    data = await state.get_data()
    product_url = data.get("product_url")
    product_name = data.get("product_name")
    sku_id = data.get("sku_id")
    await state.clear()
    await callback.answer()

    *_, sort_type = callback.data.partition("_")
    await callback.message.answer(
        text=await_message
    )

    product_data = await get_product_data(
        product_name=product_name,
        sorting_type=sort_type,
    )
    await edit_messages(
        bot=bot,
        user_id=callback.from_user.id,
        products=product_data,
    )
    await state.set_state(AwaitMessage.stars_state)
    asyncio.create_task(timeout_stars_handler(
        user_id=callback.from_user.id,
        state=state
    ))


async def timeout_stars_handler(
        user_id: int,
        state: FSMContext,
):
    await asyncio.sleep(60 * 5)  # 5 минут
    current_state = await state.get_state()
    if current_state == AwaitMessage.stars_state.state:
        await state.clear()
        builder = InlineKeyboardBuilder()
        for star in range(1, 6):
            builder.button(
                text=str(star),
                callback_data=f'star_{star}'
            )
        else:
            builder.adjust(1)
            await bot.send_message(
                chat_id=user_id,
                text=feedback_message,
                reply_markup=builder.as_markup()
            )


@router.callback_query(
    F.data.startswith("star_")
)
async def stars_handler(
        callback: CallbackQuery,
        state: FSMContext,
) -> None:
    *_, stars = callback.data.partition("_")
    await callback.message.answer(
        text=thanks_message
    )
    await state.set_state(AwaitMessage.comment_state)


@router.message(
    AwaitMessage.comment_state,
    lambda message: (
        message.text and
        'searchitems' not in message.text and
        'https' not in message.text and
        'start' not in message.text
    )
)
async def comment_handler(
        message: Message,
        state: FSMContext
):
    await state.clear()
    await message.answer(
        text=commit_message,
    )

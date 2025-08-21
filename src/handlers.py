from src.config import settings

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from src.repositories.ozon.parser import send_product_data


bot = Bot(token=settings.BOT_TOKEN)
router = Router()


class AwaitMessage(StatesGroup):
    message_text = State()


@router.message(CommandStart())
async def first_run_handler(
        message: Message
) -> None:
    await message.delete()
    await message.answer(text='Добро пожаловать')


@router.message(Command("searchitems"))
async def search_items_handler(
        message: Message
) -> None:
    await message.delete()
    builder = InlineKeyboardBuilder()
    for sort_button, sort_callback in zip(
            ('Популярные товары', 'Новинки', 'Товары дешевле', 'С высоким рейтингом'),
            ('score', 'new', 'price', 'rating')
    ):
        builder.button(
            text=sort_button,
            callback_data=f'sort_{sort_callback}'
        )
    else:
        builder.adjust(1)
        await message.answer(
            text='Выберите тип сортировки',
            reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith("sort_"))
async def sort_type_handler(
        callback: CallbackQuery,
        state: FSMContext
) -> None:
    await callback.answer()
    *_, sort_type = callback.data.partition("_")
    await state.update_data(sort_type=sort_type)
    await callback.message.answer(
        text="Отправьте ссылку на товар"
    )
    await state.set_state(AwaitMessage.message_text)


@router.message(AwaitMessage.message_text, F.text.startswith("https://"))
async def coefficient_chosen(message: Message, state: FSMContext):
    data = await state.get_data()
    sort_type = data.get("sort_type")
    product_url = message.text.strip()
    await state.clear()
    await send_product_data(
        bot=bot,
        chat_id=message.from_user.id,
        sorting_type=sort_type,
        product_url=product_url
    )
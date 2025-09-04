import asyncio

from typing import Any
from aiogram.types import URLInputFile
from aiogram import Bot

from src.repositories.ozon.answer_messages import (
    top_product_message,
    top_products_message,
    end_message
)


async def edit_messages(
        bot: Bot,
        user_id: int,
        products: dict[str, Any]
) -> None:
    product_photo = URLInputFile(products.get('product_image'))
    product_name = products.get('product_name')
    description = products.get('description')
    result_characteristics = str()
    for index, (key, value) in enumerate(products.get('characteristics', dict()).items(), start=1):
        if index <= 7:
            if value is None:
                value = ""
            elif isinstance(value, list):
                value = "; ".join(value)
            else:
                value = str(value)

            result_characteristics += f"<b>{key}</b>: <i>{value}</i>\n"
    else:
        message_text = top_product_message.format(
            product_name=product_name,
            description=description[:500],
            characteristics=result_characteristics[:],
        )
        await bot.send_photo(
            chat_id=user_id,
            photo=product_photo,
            caption=message_text,
            parse_mode='HTML',
        )

    await asyncio.sleep(2)
    top_products_str = str()
    for product_num, product in enumerate(products.get('products_data', list())[:5], start=1):
        top_product_str = "[Товар]({url}) {number} – {price}₽ | ⭐️ {rating} | 💬 {reviews}\n"
        top_products_str += top_product_str.format(
            url=product.get('url', ''),
            number=product_num,
            price=product.get('price', '0'),
            rating=product.get('rating', 'Нет'),
            reviews=product.get('reviews', 'Нет'),
        )
    else:
        currency_prices_str = "~{average_price}₽ от {min_price}₽ до {max_price}₽"
        currency_prices = products.get('currency_prices', dict())
        currency_prices_str = currency_prices_str.format(
            average_price=currency_prices.get('avg_price', ''),
            min_price=currency_prices.get('min_price', ''),
            max_price=currency_prices.get('max_price', ''),
        )

        message_text = top_products_message.format(
            top_products=top_products_str,
            currency_prices=currency_prices_str,
        )
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode='Markdown',
        )

    await asyncio.sleep(2)
    await bot.send_message(
        chat_id=user_id,
        text=end_message,
    )

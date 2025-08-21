import asyncio
import logging
import sys

from aiogram import Dispatcher

from handlers import bot, router


async def main() -> None:
    dp = Dispatcher()
    dp.include_routers(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout
    )
    asyncio.run(main())

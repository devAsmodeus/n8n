import uvicorn

from dotenv import load_dotenv
from fastapi import FastAPI

from middleware import SecretKeyCheck
from src.routers.ozon import router as oz_router


server_app = FastAPI(
    timeout=None,
    description='Проект по сбору данных'
)

# server_app.add_middleware(SecretKeyCheck)
server_app.include_router(oz_router)


if __name__ == '__main__':
    load_dotenv(dotenv_path=r'./.env')
    uvicorn.run(
        app='main:server_app',
        host='127.0.0.1',
        port=80,
        log_level='debug',
        # reload=True
    )

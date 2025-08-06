import uvicorn

from fastapi import FastAPI

from src.middleware import SecretKeyCheck
from src.routers.ozon import router as oz_router


server_app = FastAPI(
    timeout=None,
    description='Проект по сбору данных'
)

# server_app.add_middleware(SecretKeyCheck)
server_app.include_router(oz_router)


if __name__ == '__main__':
    uvicorn.run(
        app='main:server_app',
        log_level='debug',
        # reload=True
    )

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from database import Base, engine
from utils.exceptions import AppException
from routers import auth

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FPT Customer Chatbot API")


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
        headers=exc.headers,
    )


app.include_router(auth.router)
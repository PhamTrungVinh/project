from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import Base, engine
from utils.exceptions import AppException
from routers import auth, users, tickets, bookings, chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FPT Customer Chatbot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # siết lại domain cụ thể khi lên production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
        headers=exc.headers,
    )


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(bookings.router)
app.include_router(chat.router)
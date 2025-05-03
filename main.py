import asyncio
import aiohttp
from fastapi import FastAPI, Depends, Request, Form, Response, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
import dotenv
import os
import jinja2
from datetime import datetime


dotenv.load_dotenv()
DATABASE_URL = os.getenv("dburl")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="supersecretkey")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# 공유 변수와 락 선언
latest_price = None
latest_time = None
price_lock = asyncio.Lock()


# 데이터베이스 세션 생성
async def get_db():
    async with async_session() as session:
        yield session


async def get_current_price(ticker):
    url = f"https://api.upbit.com/v1/ticker?markets={ticker}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data[0]["trade_price"] if data else None


async def async_daemon():
    global latest_price, latest_time
    while True:
        price = await get_current_price("KRW-SUI")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with price_lock:
            latest_price = price
            latest_time = now
        print(f"asyncio(비동기) 데몬 실행: {price}({now})")
        await asyncio.sleep(3)


async def buy_current(coinn, price, amount):
    # 해당하는 코인 등록
    # 해당하는 KRW 등록
    # 데이터 베이스에 저장
    return True


async def sell_current(coinn, price, amount):
    # 판매하는 코인 계산
    # 판매액을 KRW로 환산
    return True


async def get_current_balance(uno):
    # 사용자별 지갑 확인
    return 0





@app.on_event("startup")
async def startup_event():
    asyncio.create_task(async_daemon())

@app.get("/")
async def root():
    return {"msg": "스레드와 asyncio를 함께 사용 중"}

@app.get("/price")
async def get_price():
    async with price_lock:
        price = latest_price
        checked_at = latest_time
    return {
        "KRW-SUI": price,
        "checked_at": checked_at
    }

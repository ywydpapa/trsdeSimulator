import asyncio
import aiohttp
from fastapi import FastAPI, Depends, Request, Form, Response, HTTPException, status, File, UploadFile
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


def format_currency(value):
    if isinstance(value, (int, float)):
        return "{:,.0f}".format(value)
    return value


templates.env.filters['currency'] = format_currency


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


async def get_current_balance(uno, db: AsyncSession = Depends(get_db)):
    try:
        query = text(f"SELECT * FROM trWallet where userNo = :uno and attrib not like :attxx")
        mycoins = await db.execute(query,{"uno":uno,"attxx":"%XXX%"})
        mycoins = mycoins.fetchall()
    except Exception as e:
        print("Error!!",e)
    finally:
        return mycoins


def require_login(request: Request):
    user_no = request.session.get("user_No")
    if not user_no:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/"},
            detail="로그인이 필요합니다."
        )
    return user_no  # 필요하다면 user_Name, user_Role도 반환 가능


@app.get("/private")
async def private_page(request: Request, user_session: int = Depends(require_login)):
    return {"msg": f"로그인된 사용자 번호: {user_session}"}


@app.on_event("startup")
async def startup_event():
    # asyncio.create_task(async_daemon())
    return True

@app.get("/")
async def login_form(request: Request):
    if request.session.get("user_No"):
        uno = request.session.get("user_No")
        return RedirectResponse(url=f"/balance/{uno}", status_code=303)
    return templates.TemplateResponse("login/login.html", {"request": request})


@app.get("/price")
async def get_price():
    async with price_lock:
        price = latest_price
        checked_at = latest_time
    return {
        "KRW-SUI": price,
        "checked_at": checked_at
    }


@app.post("/loginchk")
async def login(request: Request, response: Response, uid: str = Form(...), upw: str = Form(...),
        db: AsyncSession = Depends(get_db)):
    query = text(
        "SELECT userNo, userName, userRole FROM trUser WHERE userId = :username AND userPasswd = password(:password)")
    result = await db.execute(query, {"username": uid, "password": upw})
    user = result.fetchone()
    if user is None:
        return templates.TemplateResponse("login/login.html", {"request": request, "error": "Invalid credentials"})
    else:
        queryu = text("UPDATE trUser SET lastLogin = now() WHERE userId = :username")
        await db.execute(queryu, {"username": uid})
        await db.commit()
    # 서버 세션에 사용자 ID 저장
    request.session["user_No"] = user[0]
    request.session["user_Name"] = user[1]
    request.session["user_Role"] = user[2]
    return RedirectResponse(url=f"/balance/{user[0]}", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()  # 세션 삭제
    return RedirectResponse(url="/")


@app.get("/balanceinit/{uno}/{iniamt}")
async def init_balance(request: Request, uno: int, iniamt: float, db: AsyncSession = Depends(get_db)):
    try:
        query0 = text(f"SELECT * FROM trWallet WHERE userNo = :uno and attrib not like :attxx")
        selres = await db.execute(query0, {"uno": uno, "attxx": "%XXX%"})
        if selres.rowcount > 0:
            query = text(f"UPDATE trWallet set attrib = :attset WHERE userNo = :uno")
            await db.execute(query, {"attset": "XXXUPXXXUP", "uno": uno})
        query2 = text(f"INSERT INTO trWallet (userNo,changeType, currency,unitPrice,inAmt,remainAmt) "
                     "values (:uno, 'INITAMT','KRW', '1.0', :inamt, :inamt1)")
        await db.execute(query2, {"uno": uno, "inamt": iniamt, "inamt1": iniamt})
        await db.commit()
        mycoins = await get_current_balance(uno, db)
    except Exception as e :
        print("Init Error !!",e)
    finally:
        return templates.TemplateResponse("wallet/mywallet.html",{"request": request, "userNo": uno, "mycoins": mycoins})


@app.get("/balance/{uno}")
async def my_balance(request: Request,uno: int, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
    except Exception as e:
        print("Init Error !!", e)
        mycoins = None
    return templates.TemplateResponse("wallet/mywallet.html",{"request": request, "userNo": uno, "mycoins": mycoins})

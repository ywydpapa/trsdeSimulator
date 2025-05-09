import asyncio
import time
from typing import Dict
import math
import aiohttp
from fastapi import FastAPI, Depends, Request, Form, Response, HTTPException, status, File, UploadFile
from fastapi.encoders import jsonable_encoder
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
from aiTrader.vwmatrend import vwma_ma_cross_and_diff_noimage
from aiTrader.cprice import all_cprice


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


tradetrend: Dict = {}


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


async def get_krw_tickers():
    url = "https://api.upbit.com/v1/market/all"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            # KRW-로 시작하는 마켓만 필터링
            krw_tickers = [item for item in data if item['market'].startswith('KRW-')]
            return krw_tickers


async def update_tradetrend():
    global tradetrend
    while True:
        async for db in get_db():
            try:
                query = text("SELECT coinName FROM polarisSets WHERE attrib not like :attxxx")
                coinlist = await db.execute(query, {"attxxx": "%XXX%"})
                coinlist = coinlist.fetchall()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                timeframes = ['1d', '4h', '1h', '30m', '3m']
                result: Dict[str, Dict[str, dict]] = {}

                for coin in coinlist:
                    try:
                        result[coin[0]] = {}
                        for tf in timeframes:
                            try:
                                df, reversal_points, reversal_distances, slope, angle_deg = vwma_ma_cross_and_diff_noimage(
                                    coin[0], 3, 35, 150, tf)
                                if math.isinf(slope):
                                    if slope > 0:
                                        slope = 1e10
                                    else:
                                        slope = -1e10
                                result[coin[0]][tf] = {
                                    "slope": slope,
                                    "angle_deg": angle_deg,
                                    "reversal_count": len(reversal_points),
                                    "reversal_distances": reversal_distances,
                                }
                                time.sleep(0.2)
                            except Exception as e:
                                print(f"코인트렌드 타임프레임 처리 중 오류 발생 {tf} for {coin[0]}: {str(e)}")
                                continue
                    except Exception as e:
                        print(f"코인트렌드 처리 중 오류 발생 {coin[0]}: {str(e)}")
                        continue

                tradetrend = result
                print(f"[{now}] tradetrend updated")
            except Exception as e:
                print(f"update_tradetrend 오류 발생: {str(e)}")
            finally:
                await db.close()
        await asyncio.sleep(60)


async def buy_crypto(request, uno, coinn, price, volum, db: AsyncSession = Depends(get_db)):
    global walletkrw, walletvolum
    try:
        walletvolum = 0.0
        costkrw = volum * price
        costfee = costkrw * 0.0005
        totalcost = costkrw + costfee
        seckey = request.session.get("setupKey")
        wallets = await get_current_balance(uno, db)
        for wallet in wallets[0]:
            if wallet[5] == "KRW":
                walletkrw = wallet[9]
            elif wallet[5] == coinn:
                walletvolum = wallet[9]
        if walletkrw < totalcost:
            return False
        else:
            walletkrw = walletkrw - totalcost
            sumvolum = walletvolum + volum
            ctype = "BUY-" + coinn
            query = text("UPDATE trWallet set attrib = :xxxup WHERE userNo = :uno and currency = :coin")
            await db.execute(query, {"xxxup": 'XXXUPXXXUP', "uno": uno, "coin": "KRW"})
            await db.commit()
            query2 = text("INSERT INTO trWallet (userNo,changeType,currency,unitPrice,outAmt, remainAmt, linkNo) "
                          "values (:uno, :ctype ,'KRW', 1 , :costkrw, :remkrw, :seckey)")
            await db.execute(query2,
                             {"uno": uno, "ctype": ctype, "costkrw": totalcost, "remkrw": walletkrw, "seckey": seckey})
            await db.commit()
            query4 = text("UPDATE trWallet set attrib = :xxxup WHERE userNo = :uno and currency = :coin")
            await db.execute(query4, {"xxxup": 'XXXUPXXXUP', "uno": uno, "coin": coinn})
            await db.commit()
            query3 = text("INSERT INTO trWallet (userNo,changeType,currency,unitPrice,inAmt, remainAmt, linkNo) "
                          "values (:uno, :ctype ,:coinn, :uprice, :inamt, :remamt, :seckey)")
            await db.execute(query3, {"uno": uno, "ctype": ctype, "coinn": coinn, "uprice": price, "inamt": volum,
                                      "remamt": sumvolum, "seckey": seckey})
            await db.commit()
    except Exception as e:
        print("Error!!", e)
    return True


async def sell_crypto(request, uno, coinn, price, volum, db: AsyncSession = Depends(get_db)):
    global walletkrw, walletvolum
    try:
        walletvolum = 0.0
        costkrw = volum * price
        costfee = costkrw * 0.0005
        totalcost = costkrw - costfee
        seckey = request.session.get("setupKey")
        wallets = await get_current_balance(uno, db)
        for wallet in wallets[0]:
            if wallet[5] == "KRW":
                walletkrw = wallet[9]
            elif wallet[5] == coinn:
                walletvolum = wallet[9]
        if walletvolum < volum:
            return False
        else:
            walletkrw = walletkrw + totalcost
            sumvolum = walletvolum - volum
            ctype = "SELL-" + coinn
            query = text("UPDATE trWallet set attrib = :xxxup WHERE userNo = :uno and currency = :coin")
            await db.execute(query, {"xxxup": 'XXXUPXXXUP', "uno": uno, "coin": "KRW"})
            await db.commit()
            query2 = text("INSERT INTO trWallet (userNo,changeType,currency,unitPrice,inAmt, remainAmt, linkNo) "
                          "values (:uno, :ctype ,'KRW', 1 , :costkrw, :remkrw, :seckey)")
            await db.execute(query2,
                             {"uno": uno, "ctype": ctype, "costkrw": totalcost, "remkrw": walletkrw, "seckey": seckey})
            await db.commit()
            query4 = text("UPDATE trWallet set attrib = :xxxup WHERE userNo = :uno and currency = :coin")
            await db.execute(query4, {"xxxup": 'XXXUPXXXUP', "uno": uno, "coin": coinn})
            await db.commit()
            query3 = text("INSERT INTO trWallet (userNo,changeType,currency,unitPrice,outAmt, remainAmt, linkNo) "
                          "values (:uno, :ctype ,:coinn, :uprice, :inamt, :remamt, :seckey)")
            await db.execute(query3, {"uno": uno, "ctype": ctype, "coinn": coinn, "uprice": price, "inamt": volum,
                                      "remamt": sumvolum, "seckey": seckey})
            await db.commit()
    except Exception as e:
        print("Error!!", e)
    return True


async def get_current_balance(uno, db: AsyncSession = Depends(get_db)):
    try:
        query = text("SELECT * FROM trWallet where userNo = :uno and attrib not like :attxx order by currency ")
        result = await db.execute(query, {"uno": uno, "attxx": "%XXX%"})
        mycoins = result.fetchall()
        coinprice = {}
        for coin in mycoins:
            if coin[5] != "KRW":
                cprice = await get_current_price(coin[5])
            else:
                cprice = 1.0
            coinprice[coin[5]] = cprice
    except Exception as e:
        print("Error!!", e)
    finally:
        return mycoins, coinprice


async def get_logbook(request, uno, coinn, db: AsyncSession = Depends(get_db)):
    global mylogs
    try:
        query = text("SELECT changeType, currency,unitPrice,inAmt,outAmt,remainAmt,regDate FROM trWallet where userNo = :uno and currency = :coinn and linkNo = :seckey order by regDate ")
        result = await db.execute(query, {"uno": uno, "coinn": coinn, "seckey": request.session.get("setupKey")})
        rows = result.fetchall()
        columns = result.keys()
        data = [dict(zip(columns, row)) for row in rows]
        return jsonable_encoder(data)
    except Exception as e:
        print("Error!!", e)


async def get_avg_price(uno, setkey, coinn, db: AsyncSession = Depends(get_db)):
    try:
        query = text(
            "SELECT linkNo, regDate, changeType, currency, unitPrice, inAmt, outAmt, remainAmt, session_id, IFNULL(누적매수금액 / NULLIF(누적매수수량,0), 0) AS 매수평균단가 FROM "
            "(SELECT *,SUM(CASE WHEN changeType LIKE 'BUY%' THEN unitPrice * inAmt ELSE 0 END) OVER (PARTITION BY session_id ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS 누적매수금액,SUM(CASE WHEN changeType LIKE 'BUY%' THEN inAmt ELSE 0 END) OVER (PARTITION BY session_id ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS 누적매수수량 "
            "FROM ( SELECT *, SUM(is_zero) OVER (ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_id "
            "FROM ( SELECT *, CASE WHEN remainAmt = 0 THEN 1 ELSE 0 END AS is_zero FROM trWallet WHERE currency = :coinn and userNo = :uno ORDER BY regDate, linkNo ) t1 ) t2 ) t3 WHERE linkNo = :linkno ORDER BY regDate DESC, linkNo DESC LIMIT 1")
        result = await db.execute(query, {"coinn": coinn, "linkno": setkey, "uno": uno})
        mycoin = result.fetchone()
        return mycoin
    except Exception as e:
        print("Error!!", e)
        return None


async def get_avg_by_coin(uno,setkey ,db: AsyncSession = Depends(get_db)):
    try:
        query = text(
            "SELECT currency,IFNULL(누적매수금액 / NULLIF(누적매수수량,0), 0) AS avg_price FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY currency ORDER BY regDate DESC, linkNo DESC) AS rn,SUM(CASE WHEN changeType LIKE 'BUY%' THEN unitPrice * inAmt ELSE 0 END) OVER (PARTITION BY currency, session_id ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS 누적매수금액, SUM(CASE WHEN changeType LIKE 'BUY%' THEN inAmt ELSE 0 END)                OVER (PARTITION BY currency, session_id ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS 누적매수수량    FROM (        SELECT *,               SUM(is_zero) OVER (PARTITION BY currency ORDER BY regDate, linkNo ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_id FROM ( SELECT *, CASE WHEN remainAmt = 0 THEN 1 ELSE 0 END AS is_zero FROM trWallet WHERE userNo = :uno and linkNo = :linkno ORDER BY regDate, linkNo ) t1 ) t2) t3 WHERE rn = 1")
        result = await db.execute(query, {"uno": uno, "linkno": setkey})
        rows = result.fetchall()
        return {row.currency: round(float(row.avg_price),2) for row in rows}
    except Exception as e:
        print(e)
        return {}


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
    asyncio.create_task(update_tradetrend())
    return True


@app.get("/")
async def login_form(request: Request):
    if request.session.get("user_No"):
        uno = request.session.get("user_No")
        return RedirectResponse(url=f"/balance/{uno}", status_code=303)
    return templates.TemplateResponse("login/login.html", {"request": request})


@app.get("/initTrade/{uno}")
async def initrade(request: Request, uno: int, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    usern = request.session.get("user_Name")
    return templates.TemplateResponse("trade/inittrade.html",
                                      {"request": request, "userNo": uno, "user_Name": usern})


@app.post("/loginchk")
async def login(request: Request, response: Response, uid: str = Form(...), upw: str = Form(...),
                db: AsyncSession = Depends(get_db)):
    query = text(
        "SELECT userNo, userName, userRole, setupKey FROM trUser WHERE userId = :username AND userPasswd = password(:password)")
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
    request.session["setupKey"] = user[3]
    return RedirectResponse(url=f"/balance/{user[0]}", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()  # 세션 삭제
    return RedirectResponse(url="/")


@app.post("/balanceinit/{uno}/{iniamt}")
async def init_balance(request: Request, uno: int, iniamt: float, db: AsyncSession = Depends(get_db)):
    global seckey, mycoins
    mycoins = None
    result = {
        "success": False,
    }
    try:
        query0 = text(f"SELECT * FROM trWallet WHERE userNo = :uno and attrib not like :attxx")
        selres = await db.execute(query0, {"uno": uno, "attxx": "%XXX%"})
        if selres.rowcount > 0:
            query = text(f"UPDATE trWallet set attrib = :attset WHERE userNo = :uno")
            await db.execute(query, {"attset": "XXXUPXXXUP", "uno": uno})
        seckey = datetime.now().strftime("%Y%m%d%H%M%S")
        query2 = text(f"INSERT INTO trWallet (userNo,changeType,currency,unitPrice,inAmt, remainAmt, linkNo) "
                      "values (:uno, 'INITAMT','KRW', '1.0', :inamt, :inamt1, :seckey)")
        await db.execute(query2, {"uno": uno, "inamt": iniamt, "inamt1": iniamt, "seckey": seckey})
        await db.commit()
        query3 = text(f"UPDATE trUser set setupKey = :seckey WHERE userNo = :uno and attrib not like :attxx")
        await db.execute(query3, {"seckey": seckey, "uno": uno, "attxx": '%XXX%'})
        await db.commit()
        mycoins = await get_current_balance(uno, db)
        result = {
            "success": True,
            "setupKey": seckey,
            "userNo": uno,
            "user_Name": request.session.get("user_Name"),
        }
    except Exception as e:
        print("Init Error !!", e)
        mycoins = ([], {})
        result = {
            "success": False,
            "error": str(e)
        }
    request.session["setupKey"] = seckey
    return JSONResponse(content=result)


@app.get("/balance/{uno}")
async def my_balance(request: Request, uno: int, user_session: int = Depends(require_login),
                     db: AsyncSession = Depends(get_db)):
    global myavgp
    mycoins = None
    myavgp = None
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
        myavgp = await get_avg_by_coin(uno, request.session.get("setupKey"), db)
        print(myavgp)
    except Exception as e:
        print("Init Error !!", e)
        mycoins = None
    usern = request.session.get("user_Name")
    return templates.TemplateResponse("wallet/mywallet.html",
                                      {"request": request, "userNo": uno, "user_Name": usern, "mycoins": mycoins[0],"myavgp":myavgp,
                                       "coinprice": mycoins[1]})


@app.get("/balancecrypto/{uno}/{coinn}")
async def my_balance(request: Request, uno: int, coinn: str, user_session: int = Depends(require_login),
                     db: AsyncSession = Depends(get_db)):
    mycoin = {}
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
        myavgp = await get_avg_by_coin(uno, request.session.get("setupKey"), db)
        for coin in mycoins[0]:
            if coin[5] == coinn:
                mycoin[coin[5]] = coin[9]
                mycoin["avgPrice"] = myavgp.get(coin[5],0)
    except Exception as e:
        print("Init Error !!", e)
        mycoin = None
    return mycoin


@app.get("/tradecenter/{uno}")
async def tradecenter(request: Request, uno: int, user_session: int = Depends(require_login),
                      db: AsyncSession = Depends(get_db)):
    global coinlist
    mycoins = None
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
        coinlist = await get_krw_tickers()
    except Exception as e:
        print("Init Error !!", e)
    usern = request.session.get("user_Name")
    setkey = request.session.get("setupKey")
    return templates.TemplateResponse("trade/mytrade.html",
                                      {"request": request, "userNo": uno, "user_Name": usern, "mycoins": mycoins[0],
                                       "coinprice": mycoins[1], "setkey": setkey, "coinlist": coinlist})


@app.post("/tradebuymarket/{uno}/{coinn}/{cprice}/{volum}")
async def tradebuymarket(
        request: Request,
        uno: int,
        coinn: str,
        cprice: float,
        volum: float,
        user_session: int = Depends(require_login),
        db: AsyncSession = Depends(get_db)
):
    if uno != user_session:
        return JSONResponse({"success": False, "message": "권한이 없습니다.", "redirect": "/"})
    try:
        butm = await buy_crypto(request, uno, coinn, cprice, volum, db)
        if butm:
            # 거래 성공
            return JSONResponse({"success": True, "redirect": f"/balance/{uno}"})
        else:
            # 거래 실패
            return JSONResponse({"success": False, "message": "거래 실패", "redirect": "/tradecenter"})
    except Exception as e:
        print("Error!!", e)
        return JSONResponse({"success": False, "message": "서버 오류", "redirect": "/tradecenter"})


@app.post("/tradesellmarket/{uno}/{coinn}/{cprice}/{volum}")
async def tradesellmarket(request: Request, uno: int, coinn: str, cprice: float, volum: float, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    if uno != user_session:
        return JSONResponse({"success": False, "message": "권한이 없습니다.", "redirect": "/"})
    try:
        butm = await sell_crypto(request, uno, coinn, cprice, volum, db)
        if butm:
            # 거래 성공
            return JSONResponse({"success": True, "redirect": f"/balance/{uno}"})
        else:
            # 거래 실패
            return JSONResponse({"success": False, "message": "거래 실패", "redirect": "/tradecenter"})
    except Exception as e:
        print("Error!!", e)
        return JSONResponse({"success": False, "message": "서버 오류", "redirect": "/tradecenter"})


@app.get("/tradelogbook/{uno}")
async def tradelogbook(request: Request, uno: int, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    mycoins = None
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
    except Exception as e:
        print("Init Error !!", e)
    usern = request.session.get("user_Name")
    setkey = request.session.get("setupKey")
    return templates.TemplateResponse("trade/tradelog.html",
                                      {"request": request, "userNo": uno, "user_Name": usern, "mycoins": mycoins[0],
                                       "coinprice": mycoins[1], "setkey": setkey})


@app.get("/gettradelog/{uno}/{coinn}")
async def gettradelog(request: Request, uno: int, coinn: str, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    mylogs = None
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mylogs = await get_logbook(request, uno, coinn, db)
        print(mylogs)
        return JSONResponse({"success": True, "data": mylogs})
    except Exception as e:
        print("Get Log Error !!", e)


@app.get("/tradestatus/{uno}")
async def tradestatus(request: Request, uno: int, user_session: int = Depends(require_login), db: AsyncSession = Depends(get_db)):
    global coinlist
    mycoins = None
    if uno != user_session:
        return RedirectResponse(url="/", status_code=303)
    try:
        mycoins = await get_current_balance(uno, db)
        coinlist = await get_krw_tickers()
    except Exception as e:
        print("Init Error !!", e)
    usern = request.session.get("user_Name")
    setkey = request.session.get("setupKey")
    return templates.TemplateResponse("trade/tradestat.html",
                                      {"request": request, "userNo": uno, "user_Name": usern, "mycoins": mycoins[0],
                                       "coinprice": mycoins[1], "setkey": setkey, "coinlist": coinlist})


@app.get("/tradetrend")
async def get_tradetrend():
    return tradetrend


@app.get("/tradesignal")
async def get_tradesignal(request: Request):
    usern = request.session.get("user_Name")
    uno = request.session.get("user_No")
    return templates.TemplateResponse("trade/tradetrend.html", {"request": request,"userNo": uno, "user_Name": usern,})

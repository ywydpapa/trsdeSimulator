import requests
import pyupbit
import asyncio
import aiohttp

async def get_current_price(ticker):
    url = f"https://api.upbit.com/v1/ticker?markets={ticker}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def cprice():
    price = await get_current_price("KRW-SUI")
    print(price[0]["trade_date_kst"],price[0]["trade_time_kst"])
    print(price[0]["trade_price"])

# 비동기 루프 실행
asyncio.run(cprice())
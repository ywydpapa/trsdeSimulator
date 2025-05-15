import requests
from datetime import datetime, timezone
import time
import pandas as pd
from collections import deque, defaultdict

def all_cprice():
    server_url = "https://api.upbit.com"
    params = {"quote_currencies": "KRW"}
    res = requests.get(server_url + "/v1/ticker/all", params=params)
    data = res.json()
    result = []
    for item in data:
        market = item.get("market")
        trade_price = item.get("trade_price")
        timestamp = item.get("timestamp")
        if market and trade_price and timestamp:
            time_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
            result.append({"market": market,"trade_price": trade_price,"time_str": time_str })
    return result

max_records = 10
coin_price_history = defaultdict(lambda: deque(maxlen=max_records))

# 시간 컬럼명 생성
time_columns = ['now'] + [f'now-{i*10}s' for i in range(1, max_records)]

while True:
    price_list = all_cprice()
    for item in price_list:
        market = item['market']
        price = item['trade_price']
        coin_price_history[market].appendleft(price)  # 최신값을 맨 앞에

    # 데이터프레임 만들기
    data = []
    for market, prices in coin_price_history.items():
        # 부족한 데이터는 None으로 채움
        row = [market] + list(prices) + [None] * (max_records - len(prices))
        row = row[:max_records+1]  # market + 10개 데이터
        data.append(row)
    columns = ['market'] + time_columns
    df = pd.DataFrame(data, columns=columns)
    print(df.head())

    time.sleep(10)

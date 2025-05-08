import requests
from datetime import datetime, timezone

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
            time_str = datetime.fromtimestamp(timestamp / 1000, timezone.utc ).strftime('%Y-%m-%d %H:%M:%S')
            result.append({"market": market,"trade_price": trade_price,"timestamp": timestamp, "time_str": time_str })

    return result


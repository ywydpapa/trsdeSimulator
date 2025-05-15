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
            result.append({"market": market,"trade_price": trade_price,"time_str": time_str })
    return result


def get_upbit_orderbooks(market="KRW-BTC"):
    url = "https://api.upbit.com/v1/orderbook"
    params = {"markets": market}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return None


def get_krw_tickers():
    url = "https://api.upbit.com/v1/market/all"
    data = requests.get(url).json()
    krw_tickers = [item['market'] for item in data if item['market'].startswith('KRW-')]
    return krw_tickers


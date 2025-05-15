import pandas as pd
import numpy as np
import requests

def weighted_moving_average(series, window):
    weights = np.arange(1, window + 1)
    return series.rolling(window).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)


def get_signal(df):
    # 종가 기준
    df['WMA_120'] = weighted_moving_average(df['close'], 120)
    df['WMA_60'] = weighted_moving_average(df['close'], 60)
    df['WMA_30'] = weighted_moving_average(df['close'], 30)
    df['WMA_15'] = weighted_moving_average(df['close'], 15)
    df['WMA_3'] = weighted_moving_average(df['close'], 3)

    # 매수/매도 신호 생성
    cond_buy = (df['WMA_3'] > df['WMA_120']) & \
               (df['WMA_15'] > df['WMA_120']) & \
               (df['WMA_30'] > df['WMA_120']) & \
               (df['WMA_60'] > df['WMA_120'])
    cond_sell = (df['WMA_3'] < df['WMA_120']) & \
                (df['WMA_15'] < df['WMA_120']) & \
                (df['WMA_30'] < df['WMA_120']) & \
                (df['WMA_60'] < df['WMA_120'])

    df['signal'] = np.where(cond_buy, 'buy', np.where(cond_sell, 'sell', 'hold'))
    return df



def get_upbit_candles(market="KRW-DOGE", minutes=1, count=200):
    url = f"https://api.upbit.com/v1/candles/minutes/{minutes}"
    params = {"market": market, "count": count}
    headers = {"Accept": "application/json"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    df = pd.DataFrame(data)
    df = df.rename(columns={'candle_date_time_kst':'timestamp', 'opening_price':'open', 'high_price':'high', 'low_price':'low', 'trade_price':'close', 'candle_acc_trade_volume':'volume'})
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df = df.iloc[::-1].reset_index(drop=True)  # 시간순 정렬
    return df



df = get_upbit_candles()
result_df = get_signal(df)
print(result_df)
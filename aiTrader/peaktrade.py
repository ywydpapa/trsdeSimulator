import requests
import pandas as pd
import numpy as np
import time
from scipy.signal import find_peaks

def peak_trade_core(
        ticker='KRW-BTC',
        short_window=3,
        long_window=20,
        count=180,
        candle_unit='1m'
):
    import requests
    import pandas as pd
    from scipy.signal import find_peaks

    candle_map = {
        '1d': ('days', ''),
        '4h': ('minutes', 240),
        '1h': ('minutes', 60),
        '30m': ('minutes', 30),
        '15m': ('minutes', 15),
        '10m': ('minutes', 10),
        '5m': ('minutes', 5),
        '3m': ('minutes', 3),
        '1m': ('minutes', 1),
    }
    if candle_unit not in candle_map:
        raise ValueError(f"지원하지 않는 단위입니다: {candle_unit}")

    api_type, minute = candle_map[candle_unit]
    if api_type == 'days':
        url = f'https://api.upbit.com/v1/candles/days?market={ticker}&count={count}'
    else:
        url = f'https://api.upbit.com/v1/candles/minutes/{minute}?market={ticker}&count={count}'

    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data)
    df['candle_date_time_kst'] = pd.to_datetime(df['candle_date_time_kst'])
    df.set_index('candle_date_time_kst', inplace=True)
    df = df.sort_index(ascending=True)
    df = df[['trade_price', 'candle_acc_trade_volume']]

    # VWMA 계산
    df[f'VWMA_{short_window}'] = (
            (df['trade_price'] * df['candle_acc_trade_volume'])
            .rolling(window=short_window).sum() /
            df['candle_acc_trade_volume'].rolling(window=short_window).sum()
    )
    df[f'VWMA_{long_window}'] = (
            (df['trade_price'] * df['candle_acc_trade_volume'])
            .rolling(window=long_window).sum() /
            df['candle_acc_trade_volume'].rolling(window=long_window).sum()
    )

    vwma_short = df[f'VWMA_{short_window}'].dropna()

    # Peak, Trough 찾기
    peaks, _ = find_peaks(vwma_short, distance=3)
    troughs, _ = find_peaks(-vwma_short, distance=3)

    peak_indices = vwma_short.index[peaks]
    trough_indices = vwma_short.index[troughs]

    last_complete_time = df.index[-2] if len(df) > 1 else df.index[-1]
    last_peak_time = peak_indices[-1] if len(peak_indices) > 0 else None
    last_trough_time = trough_indices[-1] if len(trough_indices) > 0 else None

    last_extrema_type, last_extrema_time = None, None
    if last_peak_time == last_complete_time:
        last_extrema_type = '최고점'
        last_extrema_time = last_peak_time
    elif last_trough_time == last_complete_time:
        last_extrema_type = '최저점'
        last_extrema_time = last_trough_time

    # VWMA 변화율 컬럼 추가
    for window in [short_window, long_window]:
        col = f'VWMA_{window}'
        df[f'{col}_chg'] = df[col].pct_change() * 100

    # trade_price가 VWMA_short_window 보다 위/아래인지 +, - 표시와 차이값 컬럼 추가
    vwma_short_col = f'VWMA_{short_window}'
    df['price_vs_vwma'] = df['trade_price'] > df[vwma_short_col]
    df['price_vs_vwma'] = df['price_vs_vwma'].map({True: '+', False: '-'})
    df['price_vwma_diff'] = df['trade_price'] - df[vwma_short_col]
    df['price_vwma_diff'] = df['price_vwma_diff'].round(6)  # 소수점 6자리로 반올림

    # 모든 컬럼이 잘리거나 생략되지 않도록 출력
    print(last_extrema_type, last_extrema_time)
    with pd.option_context('display.max_rows', None, 'display.max_columns', None):
        print(df.tail(10))

    return last_extrema_type, last_extrema_time, df



def buy(price, time):
    print(f"[매수] {time} 가격: {price}")

def sell(price, time):
    print(f"[매도] {time} 가격: {price}")

def get_short_trend(df):
    # 마지막 3개의 trade_price 기준
    if len(df) < 3:
        return None  # 데이터 부족
    last3 = df['trade_price'].iloc[-3:]
    if last3.iloc[0] < last3.iloc[1] < last3.iloc[2]:
        return 'up'
    elif last3.iloc[0] > last3.iloc[1] > last3.iloc[2]:
        return 'down'
    else:
        return 'side'

def trade_loop(
        ticker='KRW-DOGE',
        short_window=1,
        long_window=15,
        count=120,
        candle_unit='1m'
):
    traded_times = set()  # 이미 매매한 시점 기록
    position = None       # None: 미보유, 'long': 매수(보유) 상태

    while True:
        try:
            last_extrema_type, last_extrema_time, df = peak_trade_core(
                ticker, short_window, long_window, count, candle_unit
            )
            trend = get_short_trend(df)
            if last_extrema_time is not None:
                price = df.loc[last_extrema_time, 'trade_price']
                if last_extrema_time not in traded_times:
                    if last_extrema_type == '최저점' and position is None and trend == 'up':
                        buy(price, last_extrema_time)
                        position = 'long'
                        traded_times.add(last_extrema_time)
                    elif last_extrema_type == '최고점' and position == 'long' and trend == 'down':
                        sell(price, last_extrema_time)
                        position = None
                        traded_times.add(last_extrema_time)
                    else:
                        print(f"[대기] 포지션 조건 또는 추세 불충족 (trend: {trend})")
                else:
                    print(f"[대기] 이미 해당 시점({last_extrema_time})에 매매함")
            else:
                print("[대기] 아직 매매 신호 없음")
        except Exception as e:
            print(f"에러 발생: {e}")
        time.sleep(30)


# 사용 예시
trade_loop('KRW-TRUMP', 3, 35, 120, '3m')
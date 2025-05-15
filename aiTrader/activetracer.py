import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks
import time


def peak_trade(
        ticker='KRW-BTC',
        short_window=3,
        long_window=20,
        count=180,
        candle_unit='1h'
):
    # 0. 캔들 단위 변환
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

    # 1. 데이터 가져오기
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data)
    df['candle_date_time_kst'] = pd.to_datetime(df['candle_date_time_kst'])
    df.set_index('candle_date_time_kst', inplace=True)
    df = df.sort_index(ascending=True)
    df = df[['trade_price', 'candle_acc_trade_volume']]

    # 2. VWMA 및 MA 계산
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
    df[f'MA_{short_window}'] = df['trade_price'].rolling(window=short_window).mean()
    df[f'MA_{long_window}'] = df['trade_price'].rolling(window=long_window).mean()

    # 3. 크로스 포인트 계산
    golden_cross = df[
        (df[f'VWMA_{short_window}'] > df[f'VWMA_{long_window}']) &
        (df[f'VWMA_{short_window}'].shift(1) <= df[f'VWMA_{long_window}'].shift(1))
        ]
    dead_cross = df[
        (df[f'VWMA_{short_window}'] < df[f'VWMA_{long_window}']) &
        (df[f'VWMA_{short_window}'].shift(1) >= df[f'VWMA_{long_window}'].shift(1))
        ]

    # 그래프 그리기
    fig, ax1 = plt.subplots(1, 1, figsize=(24, 8))
    valid_idx = df.index[df[f'VWMA_{long_window}'].notna()]
    ax1.plot(df['trade_price'], label='Price')
    ax1.plot(valid_idx, df.loc[valid_idx, f'VWMA_{short_window}'], label=f'VWMA {short_window}', color='blue')
    ax1.plot(valid_idx, df.loc[valid_idx, f'VWMA_{long_window}'], label=f'VWMA {long_window}', color='orange')
    ax1.scatter(golden_cross.index, golden_cross[f'VWMA_{short_window}'], color='green', label='Golden Cross',
                marker='o', s=100)
    ax1.scatter(dead_cross.index, dead_cross[f'VWMA_{short_window}'], color='red', label='Dead Cross', marker='x',
                s=100)
    ax1.set_title(f'{ticker} VWMA Cross Points ({candle_unit})')
    ax1.set_ylabel('Price')
    ax1.grid(True)
    ax1.legend()
    plt.tight_layout()
    plt.show()

    # 최근 크로스 판단
    recent = df.tail(5)
    print("최근 5개 캔들")
    print(recent[['trade_price', f'VWMA_{short_window}', f'VWMA_{long_window}']])

    # 최근 크로스 판단
    now = df.index[-1]
    now_price = df['trade_price'].iloc[-1]
    golden_times = golden_cross.index[golden_cross.index <= now]
    dead_times = dead_cross.index[dead_cross.index <= now]

    last_golden = golden_times[-1] if len(golden_times) > 0 else None
    last_dead = dead_times[-1] if len(dead_times) > 0 else None

    if last_golden and last_dead:
        if last_golden > last_dead:
            last_cross_type = 'golden'
            last_cross_time = last_golden
        else:
            last_cross_type = 'dead'
            last_cross_time = last_dead
    elif last_golden:
        last_cross_type = 'golden'
        last_cross_time = last_golden
    elif last_dead:
        last_cross_type = 'dead'
        last_cross_time = last_dead
    else:
        last_cross_type = None
        last_cross_time = None

    recent5_idx = df.index[-5:]
    recent3_idx = df.index[-3:]

    recent_golden = [idx for idx in golden_cross.index if idx in recent3_idx]
    recent_dead = [idx for idx in dead_cross.index if idx in recent3_idx]
    recent_golden_5 = [idx for idx in golden_cross.index if idx in recent5_idx]
    recent_dead_5 = [idx for idx in dead_cross.index if idx in recent5_idx]

    if recent_golden_5 and recent_dead_5:
        print("최근 5개 캔들에 골든/데드가 모두 있습니다. 매매 대기!")
        return

    if recent_golden:
        print("최근 3개 캔들에 골든크로스 발생! 매수 신호! 보유하고 있지 않다면 매수")
        now_price = df['trade_price'].iloc[-1]
        volum = 500_000 / now_price
        print(f"매수 실행: {now_price}에 {volum:.6f}코인")
        # buy_crypto(...) 호출 위치!
        return

    if recent_dead:
        print("최근 3개 캔들에 데드크로스 발생! 매도 신호! 보유중인 코인 판매")
        now_price = df['trade_price'].iloc[-1]
        print(f"매도 실행: {now_price}에 보유코인 전량")
        # sell_crypto(...) 호출 위치!
        return

    if last_cross_type is not None:
        analyze_cross_with_peak_and_vwma(
            df, last_cross_type, last_cross_time,
            short_window=short_window,
            long_window=long_window,
            threshold=0.03,  # 하락/상승 임계값 3%
            close_threshold=0.001  # VWMA 근접 임계값 0.1%
        )
    else:
        print("아직 골든/데드 크로스가 없습니다.")


def analyze_cross_with_peak_and_vwma(
    df,
    last_cross_type,
    last_cross_time,
    short_window,
    long_window,
    threshold=0.015,
    close_threshold=0.001
):
    # 1. 구간 결정
    if last_cross_type is not None and last_cross_time is not None:
        # 크로스가 있으면, 크로스 이후 데이터만 사용
        prices = df.loc[last_cross_time:]['trade_price']
        vwmashort = df.loc[last_cross_time:][f'VWMA_{short_window}']
        vwmalong = df.loc[last_cross_time:][f'VWMA_{long_window}']
        print(f"최근 크로스({last_cross_type})가 {last_cross_time}에 발생, 이후 데이터 기준으로 판단합니다.")
    else:
        # 크로스가 없으면 전체 데이터 사용
        prices = df['trade_price']
        vwmashort = df[f'VWMA_{short_window}']
        vwmalong = df[f'VWMA_{long_window}']
        print("최근 크로스가 없습니다. 전체 데이터에서 최고점/최저점 기준으로 판단합니다.")

    now_price = prices.iloc[-1]
    now_vwmalong = vwmalong.iloc[-1]
    vwma_gap = abs(now_price - now_vwmalong) / now_vwmalong

    # 최고점, 최저점 및 신호 판단
    max_price = prices.max()
    max_time = prices.idxmax()
    min_price = prices.min()
    min_time = prices.idxmin()

    fall_rate = (max_price - now_price) / max_price
    rise_rate = (now_price - min_price) / min_price

    print(f"최고가: {max_price:.2f} ({max_time}), 최저가: {min_price:.2f} ({min_time}), 현재가: {now_price:.2f}")
    print(f"최고가 대비 하락률: {fall_rate * 100:.2f}%")
    print(f"최저가 대비 상승률: {rise_rate * 100:.2f}%")

    # 신호 판단 (최고점/최저점 모두 체크)
    if fall_rate >= threshold:
        print(f"→ {threshold*100:.1f}% 이상 하락! 매도 신호!")
        print(f"→최고가 대비  {threshold * 100:.1f}% 이상 하락으로 보유 코인 전액 현재가 {now_price} 매도 실행!")
    elif vwma_gap <= close_threshold:
        print(f"→ 가격이 long VWMA({long_window})와 0.1% 이내로 접근! 추가 매도 신호!")
        print(f"→ 가격이 long VWMA({long_window})와 0.1% 이내로 접근 보유코인이 있을 경우 전액 현재가 {now_price} 매도 실행!")
    else:
        print("→ 아직 매도 신호 아님(최고가 하락 미달, long VWMA 접근 미달)")

    if rise_rate >= threshold:
        print(f"→최저가 대비  {threshold*100:.1f}% 이상 상승! 매수 신호!")
        print(f"현재가 {now_price}로 500,000원 매수")
    elif vwma_gap <= close_threshold:
        print(f"→ 가격이 long VWMA({long_window})와 0.1% 이내로 접근! 추가 매수 신호!")
        print(f"보유 코인 없을 경우 현재가 {now_price}로 500,000원 매수")
    else:
        print("→ 아직 매수 신호 아님(최저가 상승 미달, long VWMA 접근 미달)")

# 사용 예시
while True:
    peak_trade('KRW-TRUMP', 1, 45, 120, '1m')
    time.sleep(30)

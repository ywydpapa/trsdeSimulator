import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def vwma_ma_cross_and_diff(
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

    # 4. VWMA 차이 및 변동률 계산
    df['VWMA_diff'] = df[f'VWMA_{short_window}'] - df[f'VWMA_{long_window}']
    df['VWMA_diff_rate'] = df['VWMA_diff'] / df[f'VWMA_{long_window}'] * 100

    # 5. 그래프 그리기
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(24, 16), sharex=True)

    ax1.plot(df['trade_price'], label='Price')
    ax1.plot(df[f'VWMA_{short_window}'], label=f'VWMA {short_window}')
    ax1.plot(df[f'VWMA_{long_window}'], label=f'VWMA {long_window}')
    ax1.plot(df[f'MA_{short_window}'], label=f'MA {short_window}', linestyle='dotted')
    ax1.plot(df[f'MA_{long_window}'], label=f'MA {long_window}', linestyle='dotted')
    ax1.scatter(golden_cross.index, golden_cross[f'VWMA_{short_window}'], color='green', label='Golden Cross',
                marker='o')
    ax1.scatter(dead_cross.index, dead_cross[f'VWMA_{short_window}'], color='red', label='Dead Cross', marker='x')
    ax1.set_title(f'{ticker} VWMA and MA Cross Points ({candle_unit})')
    ax1.set_ylabel('Price')
    ax1.grid(True)
    ax1.legend()

    # 6. 변화율 반전 지점 찾기
    df['sign'] = df['VWMA_diff_rate'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    df['sign_change'] = df['sign'] * df['sign'].shift(1)
    # sign_change가 -1인 곳이 반전(음↔양)
    reversal_points = df[df['sign_change'] == -1]
    reversal_indices = reversal_points.index.to_list()

    # 반전 간 거리 계산 (인덱스 기준)
    reversal_distances = []
    for i in range(1, len(reversal_indices)):
        prev = reversal_indices[i-1]
        curr = reversal_indices[i]
        distance = (curr - prev).total_seconds() / 60  # 분 단위 거리
        reversal_distances.append(distance)

    # 반전 지점 표시 (그래프에)
    ax2.scatter(reversal_points.index, reversal_points['VWMA_diff_rate'], color='purple', marker='o', s=100, label='Reversal')
    ax2.plot(df.index, df['VWMA_diff_rate'], label=f'VWMA {short_window}-{long_window} Diff Rate (%)', color='orange')
    ax2.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax2.set_title(f'{ticker} VWMA {short_window}-{long_window} Diff Rate (%) ({candle_unit})')
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Diff Rate (%)')
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    plt.show()

    # 7. 마지막 반전 지점에서 현재까지의 기울기 계산
    if len(reversal_points.index) > 0:
        last_reversal_idx = reversal_points.index[-1]
        x1 = last_reversal_idx
        x2 = df.index[-1]
        y1 = df.loc[x1, 'VWMA_diff_rate']
        y2 = df.iloc[-1]['VWMA_diff_rate']
        # 시간 차이 (분)
        delta_x = (x2 - x1).total_seconds() / 60
        # 기울기 계산
        if delta_x != 0:
            slope = (y2 - y1) / delta_x
            # 각도(도)로 변환
            angle_deg = np.degrees(np.arctan(slope))
        else:
            slope = float('inf')
            angle_deg = 90.0
        print(f"마지막 반전({x1})~현재({x2}) VWMA 변화율 연결선 기울기: {slope:.4f} (%/분)")
        print(f"기울기의 각도: {angle_deg:.2f}°")
    else:
        slope = None
        angle_deg = None
        print("반전 지점이 없습니다.")

    return df, reversal_indices, reversal_distances, slope, angle_deg


def vwma_ma_cross_and_diff_noimage(
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
    if response.status_code != 200:
        raise Exception(f"API 요청 실패: {response.status_code}")
    data = response.json()
    if not data:
        raise Exception("데이터가 비어있습니다")
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

    # 4. VWMA 차이 및 변동률 계산
    df['VWMA_diff'] = df[f'VWMA_{short_window}'] - df[f'VWMA_{long_window}']
    df['VWMA_diff_rate'] = df['VWMA_diff'] / df[f'VWMA_{long_window}'] * 100

    # 5. 그래프 그리기

    # 6. 변화율 반전 지점 찾기
    df['sign'] = df['VWMA_diff_rate'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    df['sign_change'] = df['sign'] * df['sign'].shift(1)
    # sign_change가 -1인 곳이 반전(음↔양)
    reversal_points = df[df['sign_change'] == -1]
    reversal_indices = reversal_points.index.to_list()

    # 반전 간 거리 계산 (인덱스 기준)
    reversal_distances = []
    for i in range(1, len(reversal_indices)):
        prev = reversal_indices[i-1]
        curr = reversal_indices[i]
        distance = (curr - prev).total_seconds() / 60  # 분 단위 거리
        reversal_distances.append(distance)

    # 7. 마지막 반전 지점에서 현재까지의 기울기 계산
    if len(reversal_points.index) > 0:
        last_reversal_idx = reversal_points.index[-1]
        x1 = last_reversal_idx
        x2 = df.index[-1]
        y1 = df.loc[x1, 'VWMA_diff_rate']
        y2 = df.iloc[-1]['VWMA_diff_rate']
        # 시간 차이 (분)
        delta_x = (x2 - x1).total_seconds() / 60
        # 기울기 계산
        if delta_x != 0:
            slope = (y2 - y1) / delta_x
            # 각도(도)로 변환
            angle_deg = np.degrees(np.arctan(slope))
        else:
            slope = float('inf')
            angle_deg = 90.0
        print(f"마지막 반전({x1})~현재({x2}) VWMA 변화율 연결선 기울기: {slope:.4f} (%/분)")
        print(f"기울기의 각도: {angle_deg:.2f}°")
    else:
        slope = None
        angle_deg = None
        print("반전 지점이 없습니다.")

    return df, reversal_indices, reversal_distances, slope, angle_deg
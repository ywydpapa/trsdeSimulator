import requests
from datetime import datetime, timezone

def get_upbit_trade_strength(market="KRW-BTC", count=100):
    # 1. API 요청 (한 번만 실행)
    url = f"https://api.upbit.com/v1/trades/ticks?market={market}&count={count}"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("API 요청 실패:", response.status_code)
        return None, None

    trades = response.json()

    # 2. 최근 10개, 50개, 100개 데이터 나누기
    trades_10 = trades[:10]
    trades_50 = trades[:50]
    trades_100 = trades

    # 3. 체결강도 계산 함수
    def calculate_strength(trades_subset):
        buy_volume = sum(trade['trade_volume'] for trade in trades_subset if trade['ask_bid'] == 'BID')
        sell_volume = sum(trade['trade_volume'] for trade in trades_subset if trade['ask_bid'] == 'ASK')
        total_volume = buy_volume + sell_volume
        return (buy_volume / total_volume) * 100 if total_volume > 0 else 0.0

    # 4. 시간 차이 계산 함수 (밀리초 → 초 변환)
    def calculate_time_diff(trades_subset):
        if len(trades_subset) < 2:
            return 0, None, None
        start_ts = trades_subset[-1]['timestamp']
        end_ts = trades_subset[0]['timestamp']
        diff_ms = abs(end_ts - start_ts)
        diff_sec = diff_ms / 1000  # 초 단위
        # timezone-aware UTC datetime 객체로 변환
        start_time = datetime.fromtimestamp(start_ts / 1000, timezone.utc)
        end_time = datetime.fromtimestamp(end_ts / 1000, timezone.utc)
        return diff_sec, start_time, end_time

    # 5. 체결강도 및 시간차 계산
    strength_10 = calculate_strength(trades_10)
    strength_50 = calculate_strength(trades_50)
    strength_100 = calculate_strength(trades_100)

    time_diff_10, start_10, end_10 = calculate_time_diff(trades_10)
    time_diff_50, start_50, end_50 = calculate_time_diff(trades_50)
    time_diff_100, start_100, end_100 = calculate_time_diff(trades_100)

    return (
        (strength_10, time_diff_10, start_10, end_10),
        (strength_50, time_diff_50, start_50, end_50),
        (strength_100, time_diff_100, start_100, end_100)
    )

# 📌 사용 예제
market = "KRW-XRP"
(res_10, res_50, res_100) = get_upbit_trade_strength(market, count=100)

print(f"{market} 체결강도 (최근 10개): {res_10[0]:.2f}% | 시간차: {res_10[1]:.2f}초 | {res_10[2]} ~ {res_10[3]}")
print(f"{market} 체결강도 (최근 50개): {res_50[0]:.2f}% | 시간차: {res_50[1]:.2f}초 | {res_50[2]} ~ {res_50[3]}")
print(f"{market} 체결강도 (최근 100개): {res_100[0]:.2f}% | 시간차: {res_100[1]:.2f}초 | {res_100[2]} ~ {res_100[3]}")

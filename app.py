import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import os

st.set_page_config(page_title="台股成交值分析 (CSV 同步版)", layout="wide")

def get_snapshot_data(token, stock_list):
    api = DataLoader()
    api.login_by_token(api_token=token)
    df = api.taiwan_stock_tick_snapshot()
    if df is None or df.empty: return None
    
    df = df[df['stock_id'].isin(stock_list)].copy()
    
    # 1. 取得昨收價：利用當前價減去漲跌價，回推官方認定的昨收 (Reference Price)
    # 這是為了確保判斷基準與您的 CSV 一致
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['change_price'] = pd.to_numeric(df['change_price'], errors='coerce')
    df['last_close'] = df['close'] - df['change_price']
    
    # 2. 同步您的 0+1.py 邏輯：重新計算漲跌
    # 加入 0.001 的誤差容許，解決 auto_adjust 產生的 10% 判定偏差
    def judge_status(row):
        diff = row['close'] - row['last_close']
        if abs(diff) < 0.001: return "平盤"
        return "上漲" if diff > 0 else "下跌"
    
    df['status'] = df.apply(judge_status, axis=1)
    
    # 3. 計算成交值排行
    vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
    df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce')
    df['tp'] = (pd.to_numeric(df['high']) + pd.to_numeric(df['low']) + df['close']) / 3.0
    df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
    
    return df.sort_values('amount_m', ascending=False).head(300)

st.title("📊 台股成交值分析 (與 CSV 邏輯同步)")

# ... (讀取檔案與顯示邏輯)
data = get_snapshot_data(fm_token, stock_ids)

if data is not None:
    # 統計漲跌
    up = len(data[data['status'] == "上漲"])
    down = len(data[data['status'] == "下跌"])
    even = len(data[data['status'] == "平盤"])
    total = len(data)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔")
    c4.metric("漲跌比", f"{up/down:.2f}" if down > 0 else "N/A")

    st.subheader("前 300 名詳細清單 (計算基準檢查)")
    st.dataframe(data[['stock_id', 'stock_name', 'close', 'last_close', 'status', 'amount_m']])

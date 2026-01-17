import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from FinMind.data import DataLoader
from datetime import datetime
import os
import requests

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股即時成交值監控 (同步版)", layout="wide")

def get_snapshot_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        if df is None or df.empty: return None
        
        # 1. 篩選名單
        df = df[df['stock_id'].isin(stock_list)].copy()
        
        # 2. 轉為數值 (確保計算正確)
        for col in ['close', 'high', 'low', 'total_volume', 'change_price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 3. 同步原始程式邏輯：使用 Typical Price (H+L+C)/3
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        
        # 4. 計算成交金額 (百萬)
        df['amount_m'] = (df['tp'] * df['total_volume']) / 1_000_000.0
        
        # 5. 排序並取前 300 名 (這決定了統計的基礎)
        df = df.sort_values('amount_m', ascending=False).head(300)
        return df
    except Exception as e:
        st.error(f"資料獲取失敗: {e}")
        return None

# =========================
# Streamlit 網頁介面
# =========================
st.title("📊 台股成交值前 300 名分析 (同步邏輯版)")

with st.sidebar:
    st.header("⚙️ 設定")
    fm_token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 手動更新數據"):
        st.rerun()

# 讀取股票清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
    # 移除指數，只留個股 (同步原始程式邏輯)
    stock_ids = [s for s in stock_ids if s.isdigit()]
else:
    stock_ids = []

data = get_snapshot_data(fm_token, stock_ids)

if data is not None and not data.empty:
    # 統計漲跌
    up = len(data[data['change_price'] > 0])
    down = len(data[data['change_price'] < 0])
    even = len(data[data['change_price'] == 0])
    total = len(data)
    
    # 指標顯示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔")
    ratio = up/down if down != 0 else 0
    c4.metric("漲跌比", f"{ratio:.2f}")

    # 表格顯示 (與 CSV 欄位盡量靠攏)
    st.subheader("前 10 名成交值明細 (與原始程式邏輯同步)")
    res_df = data[['stock_id', 'stock_name', 'close', 'change_price', 'amount_m']].head(10)
    res_df.columns = ['代號', '名稱', '收盤', '漲跌', '成交金額(百萬)']
    st.table(res_df)

    # 完整清單
    with st.expander("展開前 300 名清單"):
        st.dataframe(data[['stock_id', 'stock_name', 'close', 'high', 'low', 'total_volume', 'amount_m']])
else:
    st.info("無法讀取資料，請檢查 Token 或檔案。")

import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback
import time

# ==========================================
# 版本與診斷區 (Version & Debug)
# ==========================================
VERSION = "V8.0 (終極修復版)"
CHANGELOG = """
1. 修正 yfinance 資料欄位提取邏輯 (處理多層索引)
2. 加入自動重試 (Retry) 機制，提高 3707 成功率
3. 加入詳細 Debug 資訊輸出，方便排錯
4. 移除 auto_adjust 以提升資料穩定性
"""

st.set_page_config(page_title=f"台股分析 {VERSION}", layout="wide")

def get_ma5_v8(token, stock_list):
    api = DataLoader()
    api.login_by_token(api_token=token)
    
    # 1. 快照與排行
    df_snap = api.taiwan_stock_tick_snapshot()
    if df_snap is None or df_snap.empty:
        return None, "FinMind API 快照獲取失敗。"
    
    df_snap['stock_id'] = df_snap['stock_id'].astype(str)
    df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
    
    v_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
    for c in ['close', 'high', 'low', v_col]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    df = df.dropna(subset=['close', 'high', 'low', v_col])
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
    df['amount_m'] = (df['tp'] * df[v_col]) / 1_000_000.0
    top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()

    # 2. 獲取 MA5
    results = []
    p_bar = st.progress(0)
    status_text = st.empty()
    
    for i, (idx, row) in enumerate(top_300.iterrows()):
        sid = row['stock_id']
        curr_price = row['close']
        status_text.write(f"🔍 處理中 ({i+1}/300): {sid}")
        
        hist_close = None
        # 救援機制：嘗試不同後綴
        for suffix in [".TW", ".TWO"]:
            try:
                # 設定 threads=False 避免雲端多執行緒衝突
                temp = yf.download(f"{sid}{suffix}", period="1mo", interval="1d", progress=False, threads=False, auto_adjust=False)
                if not temp.empty:
                    # 處理 Close 欄位 (yfinance 2.x 版有時會回傳多層索引)
                    if 'Close' in temp.columns:
                        hist_close = temp['Close'].dropna()
                    elif ('Close', f"{sid}{suffix}") in temp.columns:
                        hist_close = temp[('Close', f"{sid}{suffix}")].dropna()
                    
                    if hist_close is not None and not hist_close.empty:
                        break
            except:
                continue
        
        # 3. 計算 MA5
        if hist_close is not None and len(hist_close) >= 4:
            # 取最近 4 天收盤價
            past_4 = hist_close.tail(4).tolist()
            ma5 = (sum(past_4) + curr_price) / 5.0
            status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
        else:
            ma5 = None
            status_str = "資料不足 (Yahoo 未回傳有效數據)"
            
        results.append({
            "代號": sid,
            "名稱": row.get('stock_name', ''),
            "目前價": curr_price,
            "五日均價": round(ma5, 2) if ma5 else None,
            "狀態": status_str,
            "成交值(百萬)": round(row['amount_m'], 1)
        })
        p_bar.progress((i + 1) / len(top_300))
        
    status_text.empty()
    return pd.DataFrame(results), "成功"

# =========================
# UI 呈現
# =========================
st.markdown(f"<h1 style='color: red;'>⚠️ 目前版本：{VERSION}</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📋 更新紀錄")
    st.info(CHANGELOG)
    st.divider()
    if st.button("🔄 重新載入"):
        st.rerun()

if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

# 安全執行區域
try:
    data, msg = get_ma5_v8("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", stock_ids)
    
    if data is not None:
        above = len(data[data['狀態'] == "站上 MA5"])
        below = len(data[data['狀態'] == "跌破 MA5"])
        c1, c2, c3 = st.columns(3)
        c1.metric("站上 MA5", f"{above} 檔")
        c2.metric("跌破 MA5", f"{below} 檔")
        c3.metric("有效樣本", f"{above + below} 檔")
        
        st.divider()
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.error(f"分析失敗：{msg}")
except Exception as e:
    st.error("💣 程式發生未預期錯誤")
    st.subheader("🛠️ 偵錯資訊 (Debug Console)")
    st.code(traceback.format_exc()) # 這裡會印出真正的錯誤原因

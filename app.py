import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback
import time

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股 MA5 穩定版 (yfinance)", layout="wide")

def get_ma5_logic(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取 FinMind 快照 (決定前 300 名排行)
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "FinMind API 未回傳快照數據。"
        
        # 篩選名單
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        for c in ['close', 'high', 'low', vol_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        df = df.dropna(subset=['close', 'high', 'low', vol_col])
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
        
        # 2. 透過 yfinance 分批下載歷史資料 (解決資料不足核心問題)
        st.info("正在分批同步 300 檔個股之 yfinance 歷史數據...")
        top_ids = top_300['stock_id'].tolist()
        
        # 用來存放所有歷史收盤價的字典
        hist_master = {}
        
        # 分批處理，每組 20 檔，避免被 Yahoo 封鎖
        chunk_size = 20
        progress_bar = st.progress(0)
        
        for i in range(0, len(top_ids), chunk_size):
            chunk = top_ids[i:i + chunk_size]
            # 同時準備上市與上櫃代號
            batch_tickers = [f"{s}.TW" for s in chunk] + [f"{s}.TWO" for s in chunk]
            
            # 下載 7 天資料 (足夠取前 4 日收盤)
            try:
                # 使用 group_by='ticker' 讓資料結構更好處理
                batch_data = yf.download(batch_tickers, period="7d", interval="1d", progress=False, group_by='ticker')
                
                for sid in chunk:
                    # 優先找 .TW，找不到或空值再找 .TWO
                    for suffix in [".TW", ".TWO"]:
                        ticker = f"{sid}{suffix}"
                        if ticker in batch_data.columns.levels[0]:
                            s_data = batch_data[ticker]['Close'].dropna()
                            if not s_data.empty:
                                hist_master[sid] = s_data.tolist()
                                break
            except:
                pass
            
            # 更新進度條
            progress_bar.progress(min((i + chunk_size) / len(top_ids), 1.0))

        # 3. 計算 MA5 狀態
        results = []
        for _, row in top_300.iterrows():
            sid = row['stock_id']
            curr_price = row['close']
            
            # 判定邏輯
            if sid in hist_master:
                # 取得過去的收盤價 (排除今天，如果 yf 已經含今天則取最後 4 筆)
                past_closes = hist_master[sid]
                # 為確保計算的是「今日價 + 過去 4 日」，我們取歷史資料扣除最後一筆(若為今日)後的 4 筆
                # 簡易作法：取最後 4 筆作為歷史基底
                recent_closes = past_closes[-4:]
                
                if len(recent_closes) >= 4:
                    ma5 = (sum(recent_closes) + curr_price) / 5.0
                    status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
                else:
                    status_str = "資料不足"
                    ma5 = None
            else:
                status_str = "資料不足"
                ma5 = None
            
            results.append({
                "代號": sid,
                "名稱": row.get('stock_name', ''),
                "目前價": curr_price,
                "五日均價": round(ma5, 2) if ma5 else None,
                "狀態": status_str,
                "成交值(百萬)": round(row['amount_m'], 1)
            })
            
        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# 網頁 UI
# =========================
st.title("📈 台股成交值前 300 名 - MA5 分析 (分批穩定版)")

with st.sidebar:
    st.header("⚙️ 系統設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 重新掃描市場"):
        st.rerun()

if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

data, msg = get_ma5_logic(token, stock_ids)

if data is not None:
    # 指標
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = above + below
    
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("總分析數", f"{total} 檔")

    st.divider()
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.error("發生錯誤，請檢查下方日誌：")
    st.code(msg)

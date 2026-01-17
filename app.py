import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback
import time

# ==========================================
# V12.0 診斷看板
# ==========================================
VERSION = "V12.0 (全診斷回報版)"

st.set_page_config(page_title=f"MA5 分析 {VERSION}", layout="wide")
st.markdown(f"<h1 style='color: white; background-color: #007BFF; padding: 10px; text-align: center;'>⚠️ 目前執行版本：{VERSION}</h1>", unsafe_allow_html=True)

# =========================
# 核心抓取邏輯
# =========================
def get_ma5_v12(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取快照
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "FinMind API 未回傳數據，請確認 Token 是否正確。"
        
        df_snap['stock_id'] = df_snap['stock_id'].astype(str)
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        
        # 2. 計算成交值
        v_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        for c in ['close', 'high', 'low', v_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low', v_col])
        
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[v_col]) / 1_000_000.0
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()

        # 3. 逐一抓取 yfinance (加入詳細診斷)
        results = []
        p_bar = st.progress(0)
        
        for i, (idx, row) in enumerate(top_300.iterrows()):
            sid = row['stock_id']
            curr_price = row['close']
            
            hist_close = None
            diag_info = "Yahoo 未回傳"
            
            for suffix in [".TW", ".TWO"]:
                try:
                    # 使用 yfinance 抓取一個月歷史資料
                    tk = yf.Ticker(f"{sid}{suffix}")
                    tmp = tk.history(period="1mo", interval="1d")
                    if not tmp.empty:
                        # 確保抓到 Close 欄位
                        hist_close = tmp['Close'].dropna()
                        if not hist_close.empty:
                            break
                    else:
                        diag_info = f"Yahoo 回傳空值 ({sid}{suffix})"
                except Exception as e:
                    diag_info = f"連線錯誤: {str(e)}"
            
            # 4. 計算 MA5: (今日價 + 前四日收盤) / 5
            if hist_close is not None and len(hist_close) >= 4:
                past_4 = hist_close.tail(4).tolist()
                ma_val = (sum(past_4) + curr_price) / 5.0
                status = "站上 MA5" if curr_price >= ma_val else "跌破 MA5"
            else:
                ma_val = None
                status = f"資料不足 ({diag_info})"
            
            results.append({
                "代號": sid,
                "名稱": row.get('stock_name', ''),
                "目前價": curr_price,
                "五日均價": round(ma_val, 2) if ma_val else None,
                "狀態": status,
                "成交值(百萬)": round(row['amount_m'], 1)
            })
            p_bar.progress((i + 1) / len(top_300))
            
        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# UI 側邊欄與分析按鈕
# =========================
with st.sidebar:
    st.header("📋 系統狀態")
    if os.path.exists("全台股股票.txt"):
        st.success("✅ 找到股票清單")
        with open("全台股股票.txt", "r", encoding="utf-8") as f:
            stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
    else:
        st.error("❌ 找不到 全台股股票.txt")
        stock_ids = []

    st.divider()
    analyze_btn = st.button("🚀 開始全市場分析", type="primary")

# 執行分析
if analyze_btn and stock_ids:
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk"
    
    data, log_msg = get_ma5_v12(token, stock_ids)
    
    if data is not None:
        above = len(data[data['狀態'] == "站上 MA5"])
        below = len(data[data['狀態'] == "跌破 MA5"])
        total = above + below
        
        c1, c2, c3 = st.columns(3)
        c1.metric("站上 MA5", f"{above} 檔")
        c2.metric("跌破 MA5", f"{below} 檔")
        c3.metric("有效分析數", f"{total} 檔")
        
        st.divider()
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.error("💣 程式執行中斷，錯誤代碼如下：")
        st.code(log_msg)

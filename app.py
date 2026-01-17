import streamlit as st
import os
import sys

# ==========================================
# V10.0 核心檢查區 (最優先執行)
# ==========================================
VERSION = "V10.0 (全環境檢查版)"

st.set_page_config(page_title=f"MA5 分析 {VERSION}", layout="wide")

# 1. 顯示版本 (確保使用者看到的是新版)
st.markdown(f"<h1 style='color: white; background-color: red; padding: 10px; text-align: center;'>⚠️ 目前執行版本：{VERSION}</h1>", unsafe_allow_html=True)

# 2. 環境診斷 (檢查套件是否存在)
missing_packages = []
try:
    import yfinance as yf
except ImportError:
    missing_packages.append("yfinance")
try:
    from FinMind.data import DataLoader
except ImportError:
    missing_packages.append("FinMind")

if missing_packages:
    st.error(f"❌ 缺少必要套件: {', '.join(missing_packages)}")
    st.info("請檢查 GitHub 上的 requirements.txt 是否包含這些套件名稱。")
    st.stop()

# ==========================================
# 程式主邏輯
# ==========================================
import pandas as pd
from datetime import datetime
import traceback
import time

def get_ma5_v10(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 抓取快照
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "FinMind 快照抓取失敗"
        
        df_snap['stock_id'] = df_snap['stock_id'].astype(str)
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        
        # 數值轉換
        v_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        for c in ['close', 'high', 'low', v_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low', v_col])
        
        # 成交值計算
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[v_col]) / 1_000_000.0
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()

        # 逐筆抓取
        results = []
        p_bar = st.progress(0)
        for i, (idx, row) in enumerate(top_300.iterrows()):
            sid = row['stock_id']
            curr_price = row['close']
            
            # yfinance 抓取邏輯 (單兵救援)
            hist_close = None
            for suffix in [".TW", ".TWO"]:
                try:
                    # 抓取 1 個月資料，關閉多線程增加穩定性
                    tk = yf.Ticker(f"{sid}{suffix}")
                    tmp = tk.history(period="1mo")['Close']
                    if not tmp.empty:
                        hist_close = tmp.dropna()
                        break
                except: continue
            
            # 計算
            if hist_close is not None and len(hist_close) >= 4:
                past_4 = hist_close.tail(4).tolist()
                ma5 = (sum(past_4) + curr_price) / 5.0
                status = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
            else:
                ma5 = None
                status = "資料不足"
            
            results.append({
                "代號": sid, "目前價": curr_price, "五日均價": round(ma5, 2) if ma5 else None,
                "狀態": status, "成交值(百萬)": round(row['amount_m'], 1)
            })
            p_bar.progress((i + 1) / len(top_300))
            
        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# UI 側邊欄與執行
# =========================
with st.sidebar:
    st.header("📂 檔案檢查")
    if os.path.exists("全台股股票.txt"):
        st.success("✅ 找到 全台股股票.txt")
        with open("全台股股票.txt", "r", encoding="utf-8") as f:
            stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
    else:
        st.error("❌ 找不到 全台股股票.txt")
        stock_ids = []
    
    st.divider()
    if st.button("🚀 啟動分析"):
        st.rerun()

# 執行區
if stock_ids:
    try:
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk"
        data, msg = get_ma5_v10(token, stock_ids)
        
        if data is not None:
            st.dataframe(data, use_container_width=True)
        else:
            st.error("❌ 執行失敗")
            st.code(msg)
    except Exception:
        st.code(traceback.format_exc())

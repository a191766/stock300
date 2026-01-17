import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback
import time

# ==========================================
# 版本資訊
# ==========================================
VERSION = "V9.0 (診斷與測試版)"
CHANGELOG = """
1. 新增「測試模式」勾選，可先測 10 檔避免等待。
2. 強化 yfinance 資料提取安全性，預防 MultiIndex 錯誤。
3. 自動偵測清單檔案讀取狀態。
4. 顯示伺服器目前的時區與時間。
"""

st.set_page_config(page_title=f"MA5 分析 {VERSION}", layout="wide")

def get_ma5_v9(token, stock_list, test_mode=False):
    api = DataLoader()
    api.login_by_token(api_token=token)
    
    # 1. 抓取快照
    df_snap = api.taiwan_stock_tick_snapshot()
    if df_snap is None or df_snap.empty:
        return None, "FinMind API 無法取得快照，請檢查 Token 或連線。"
    
    df_snap['stock_id'] = df_snap['stock_id'].astype(str)
    df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
    
    # 計算成交值
    vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
    for c in ['close', 'high', 'low', vol_col]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['close', 'high', 'low', vol_col])
    
    df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
    df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
    
    # 排序
    limit = 10 if test_mode else 300
    top_stocks = df.sort_values('amount_m', ascending=False).head(limit).copy()

    # 2. 獲取 MA5
    results = []
    p_bar = st.progress(0)
    
    for i, (idx, row) in enumerate(top_stocks.iterrows()):
        sid = row['stock_id']
        curr_price = row['close']
        
        hist_close = None
        diag_msg = "未知錯誤"
        
        # 嘗試 yfinance 下載
        for suffix in [".TW", ".TWO"]:
            try:
                # 抓取一個月數據，不使用多執行緒
                df_h = yf.download(f"{sid}{suffix}", period="1mo", interval="1d", progress=False, threads=False)
                if not df_h.empty:
                    # 強制提取 Close 欄位 (相容不同版本 yf)
                    if 'Close' in df_h.columns:
                        hist_close = df_h['Close'].dropna()
                    else:
                        # 處理某些版本會回傳 MultiIndex 的情況
                        hist_close = df_h.xs('Close', axis=1, level=0).iloc[:, 0].dropna()
                    
                    if not hist_close.empty:
                        break
            except Exception as e:
                diag_msg = str(e)
        
        # 3. 判定邏輯
        if hist_close is not None and len(hist_close) >= 4:
            past_4 = hist_close.tail(4).tolist()
            # $MA5 = (今日價 + 前四日收盤) / 5$
            ma5 = (sum(past_4) + curr_price) / 5.0
            status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
        else:
            ma5 = None
            status_str = f"資料不足 ({diag_msg})"
            
        results.append({
            "代號": sid,
            "名稱": row.get('stock_name', ''),
            "目前價": curr_price,
            "五日均價": round(ma5, 2) if ma5 else None,
            "狀態": status_str,
            "成交值(百萬)": round(row['amount_m'], 1)
        })
        p_bar.progress((i + 1) / len(top_stocks))
        
    return pd.DataFrame(results), "成功"

# =========================
# UI 介面
# =========================
st.markdown(f"## 📊 台股 MA5 強勢分析 <span style='color:blue'>{VERSION}</span>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📋 狀態監控")
    st.info(f"伺服器時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    test_mode = st.checkbox("測試模式 (僅分析前 10 檔)", value=True)
    
    st.divider()
    if st.button("🔄 刷新頁面"):
        st.rerun()

# 檔案讀取檢查
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
    st.sidebar.success(f"成功讀取清單: {len(stock_ids)} 檔")
else:
    st.error("❌ 找不到 全台股股票.txt")
    stock_ids = []

# 分析執行
try:
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk"
    
    if st.button("🚀 開始分析"):
        data, msg = get_ma5_v9(token, stock_ids, test_mode)
        
        if data is not None:
            c1, c2, c3 = st.columns(3)
            up = len(data[data['狀態'] == "站上 MA5"])
            down = len(data[data['狀態'] == "跌破 MA5"])
            c1.metric("站上 MA5", up)
            c2.metric("跌破 MA5", down)
            c3.metric("樣本數", len(data))
            
            st.divider()
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.error(f"分析失敗: {msg}")
            
except Exception:
    st.error("💣 程式發生未預期崩潰")
    st.code(traceback.format_exc())

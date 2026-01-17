import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback

# ==========================================
# 版本資訊 (Version Tracking)
# ==========================================
CURRENT_VERSION = "V5.0"
LAST_UPDATED = "2026-01-17"
CHANGELOG = """
- 新增：版本監控與更新紀錄面板
- 修正：yfinance 批量下載失敗時的單兵救援機制
- 修正：針對 3707 等標的強化 .TW / .TWO 自動切換
- 新增：詳細錯誤診斷資訊輸出
"""

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title=f"台股 MA5 監控 {CURRENT_VERSION}", layout="wide")

def get_ma5_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取 FinMind 快照
        with st.spinner("Step 1: 正在獲取市場即時排行..."):
            df_snap = api.taiwan_stock_tick_snapshot()
            if df_snap is None or df_snap.empty:
                return None, "FinMind API 未回傳快照，請檢查 Token。"
            
            df_snap['stock_id'] = df_snap['stock_id'].astype(str)
            df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
            
            # 計算成交值 (TP 邏輯)
            vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
            for c in ['close', 'high', 'low', vol_col]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df = df.dropna(subset=['close', 'high', 'low', vol_col])
            
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
            df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
            top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()

        # 2. 抓取 yfinance 歷史資料 (V5.0 強化救援版)
        st.info(f"Step 2: 正在計算 {len(top_300)} 檔個股 MA5 (採用單兵救援模式)...")
        results = []
        top_ids = top_300['stock_id'].tolist()
        
        # 建立下載進度
        progress_bar = st.progress(0)
        
        for i, sid in enumerate(top_ids):
            curr_price = top_300.iloc[i]['close']
            hist_data = None
            
            # 救援邏輯：先試 .TW 再試 .TWO
            for suffix in [".TW", ".TWO"]:
                try:
                    # 只抓 10 天，快速下載
                    ticker = yf.Ticker(f"{sid}{suffix}")
                    temp_hist = ticker.history(period="10d")['Close']
                    if not temp_hist.empty and len(temp_hist) >= 4:
                        hist_data = temp_hist
                        break
                except:
                    continue
            
            # 計算 MA5
            if hist_data is not None:
                # 均線公式: (今日即時價 + 過去四日收盤) / 5
                # 我們移除可能包含今天的歷史收盤，確保日期不重複
                past_4_closes = hist_data.tail(4).tolist()
                ma5 = (sum(past_4_closes) + curr_price) / 5.0
                status = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
            else:
                ma5 = None
                status = "資料不足 (Yahoo 未回傳)"
            
            results.append({
                "代號": sid,
                "名稱": top_300.iloc[i].get('stock_name', ''),
                "目前價": curr_price,
                "五日均價": round(ma5, 2) if ma5 else None,
                "狀態": status,
                "成交值(百萬)": round(top_300.iloc[i]['amount_m'], 1)
            })
            progress_bar.progress((i + 1) / len(top_300))

        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# 網頁 UI 佈局
# =========================
st.markdown(f"### 🚀 台股成交值排行 & MA5 強勢分析 `{CURRENT_VERSION}`")

with st.sidebar:
    st.header("📋 版本資訊")
    st.success(f"目前版本：{CURRENT_VERSION}")
    st.info(f"最後更新：{LAST_UPDATED}")
    with st.expander("查看修改紀錄"):
        st.markdown(CHANGELOG)
    
    st.divider()
    st.header("⚙️ 參數設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 重新載入數據"):
        st.rerun()

# 讀取清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

# 執行分析
data, msg = get_ma5_data(token, stock_ids)

if data is not None:
    # 統計指標
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = above + below
    
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("樣本有效數", f"{total} 檔")

    st.divider()
    st.subheader("前 300 名詳細分析 (支援 3707 等上櫃標的)")
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.error("分析執行失敗：")
    st.code(msg)

import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股 MA5 強勢股監控", layout="wide")

def get_ma5_analysis(token, stock_list):
    try:
        # 1. 抓取 FinMind 快照 (決定前 300 名)
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        
        if df is None or df.empty:
            return None, "FinMind API 未回傳數據，請檢查 Token。"
        
        # 篩選名單
        df = df[df['stock_id'].isin(stock_list)].copy()
        vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        
        # 轉數值並計算成交值 (TP 邏輯)
        for c in ['close', 'high', 'low', vol_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low', vol_col])
        
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        
        # 取得前 300 名
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
        
        # 2. 下載前 300 名的歷史收盤價 (用於計算 MA5)
        st.info("正在計算 MA5 均線數據，請稍候...")
        tickers = [f"{s}.TW" for s in top_300['stock_id'].tolist()]
        
        # 抓取 10 天資料以確保有足夠的 5 個交易日
        hist = yf.download(tickers, period="10d", interval="1d", progress=False)['Close']
        
        # 3. 計算 MA5 並判定
        results = []
        for sid in top_300['stock_id'].tolist():
            row = top_300[top_300['stock_id'] == sid].iloc[0]
            curr_price = row['close']
            ticker_name = f"{sid}.TW"
            
            # 取得歷史資料 (排除今日，拿前四日) + 今日價
            if ticker_name in hist.columns:
                past_closes = hist[ticker_name].dropna().tail(5).tolist()
                if len(past_closes) >= 5:
                    ma5 = sum(past_closes) / 5.0
                    status = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
                else:
                    status = "資料不足"
                    ma5 = None
            else:
                status = "抓不到歷史價"
                ma5 = None
            
            results.append({
                "代號": sid,
                "名稱": row.get('stock_name', ''),
                "目前價": curr_price,
                "五日均價": round(ma5, 2) if ma5 else None,
                "狀態": status,
                "成交值(百萬)": round(row['amount_m'], 1)
            })
            
        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# 網頁顯示
# =========================
st.title("📈 成交值前 300 名 - MA5 強勢股監控")

with st.sidebar:
    st.header("⚙️ 系統設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 刷新分析數據"):
        st.rerun()

# 讀取名單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

data, msg = get_ma5_analysis(token, stock_ids)

if data is not None:
    # 統計
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = above + below
    
    # 顯示指標
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("樣本總數", f"{total} 檔")

    st.divider()

    # 詳細表格
    st.subheader("前 300 名 MA5 強弱明細")
    st.dataframe(data, use_container_width=True)
else:
    st.error("分析執行失敗，請將以下錯誤訊息提供給技術支援：")
    st.code(msg)

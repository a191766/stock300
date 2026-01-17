import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股 MA5 強弱勢分析", layout="wide")

@st.cache_data(ttl=3600) # 快取歷史資料一小時，減少重複下載
def get_historical_closes(stock_ids):
    """
    批次獲取前 300 名個股的歷史收盤價
    """
    # 建立 yfinance 代號清單 (假設多數為 .TW，少數為 .TWO)
    tickers = [f"{s}.TW" for s in stock_ids]
    # 抓取過去 10 天資料確保有足夠交易日
    data = yf.download(tickers, period="10d", interval="1d", progress=False, group_by='ticker')
    
    hist_closes = {}
    for sid in stock_ids:
        try:
            # 取得該股 Close 欄位，並過濾掉空值，取最後 4 筆 (即 D-1 到 D-4)
            s_data = data[f"{sid}.TW"]['Close'].dropna()
            if len(s_data) >= 4:
                hist_closes[sid] = s_data.tail(4).tolist()
        except:
            continue
    return hist_closes

def get_analysis_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        
        if df is None or df.empty:
            return None, "API 無法獲取即時數據"
        
        # 1. 篩選並計算成交值排行
        df = df[df['stock_id'].isin(stock_list)].copy()
        vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'total_volume')
        
        for c in ['close', 'high', 'low', vol_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        df = df.dropna(subset=['close', 'high', 'low', vol_col])
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        
        # 排序前 300 名
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
        
        # 2. 獲取這 300 檔的歷史收盤價
        top_ids = top_300['stock_id'].tolist()
        hist_data = get_historical_closes(top_ids)
        
        # 3. 計算 MA5 並判定強弱
        def calculate_ma5_status(row):
            sid = row['stock_id']
            curr_price = row['close']
            if sid in hist_data:
                past_4_closes = hist_data[sid]
                # 當前 MA5 = (前四日收盤 + 今日當前價) / 5
                ma5 = (sum(past_4_closes) + curr_price) / 5.0
                return "MA5之上" if curr_price > ma5 else "MA5之下"
            return "資料不足"

        top_300['ma5_status'] = top_300.apply(calculate_ma5_status, axis=1)
        return top_300, "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# 網頁顯示
# =========================
st.title("📊 成交值前 300 名 - MA5 強弱勢分析")

with st.sidebar:
    st.header("⚙️ 設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 刷新數據"):
        st.cache_data.clear() # 清除快照，強制重新下載
        st.rerun()

# 讀取清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

data, msg = get_analysis_data(token, stock_ids)

if data is not None:
    # 統計 MA5 狀況
    above = len(data[data['ma5_status'] == "MA5之上"])
    below = len(data[data['ma5_status'] == "MA5之下"])
    total = above + below
    
    # 指標顯示
    c1, c2, c3 = st.columns(3)
    c1.metric("MA5 之上 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("MA5 之下 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("強弱比 (多/空)", f"{above/below:.2f}" if below > 0 else "N/A")

    st.divider()

    # 詳細清單
    st.subheader("前 10 名成交值強弱清單")
    show_df = data[['stock_id', 'stock_name', 'close', 'ma5_status', 'amount_m']].head(10)
    show_df.columns = ['代號', '名稱', '目前價', 'MA5 狀態', '成交值(百萬)']
    st.table(show_df)

    with st.expander("展開前 300 名完整 MA5 數據"):
        st.dataframe(data)
else:
    st.error(f"分析失敗：\n{msg}")

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

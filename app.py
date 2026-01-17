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
st.set_page_config(page_title="台股 MA5 監控 (yfinance 同步版)", layout="wide")

def get_ma5_by_yfinance(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取 FinMind 快照決定前 300 名
        with st.status("正在抓取市場快照...", expanded=True) as status:
            df_snap = api.taiwan_stock_tick_snapshot()
            if df_snap is None or df_snap.empty:
                return None, "FinMind API 未回傳快照數據。"
            
            # 過濾清單並轉數值
            df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
            vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
            for c in ['close', 'high', 'low', vol_col]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            
            df = df.dropna(subset=['close', 'high', 'low', vol_col])
            # 計算成交值 (TP 邏輯)
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
            df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
            top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
            
            status.update(label="已選定前 300 名，正在透過 yfinance 抓取歷史均線...", state="running")

            # 2. 準備 yfinance 代號 (同時嘗試上市與上櫃)
            top_ids = top_300['stock_id'].tolist()
            # 建立兩種可能的代號，例如 3707.TW 與 3707.TWO
            tw_tickers = [f"{s}.TW" for s in top_ids]
            two_tickers = [f"{s}.TWO" for s in top_ids]
            all_tickers = tw_tickers + two_tickers
            
            # 抓取 10 天歷史資料 (包含昨日)
            hist = yf.download(all_tickers, period="10d", interval="1d", progress=False)['Close']
            
            # 3. 計算 MA5 狀態
            results = []
            for _, row in top_300.iterrows():
                sid = row['stock_id']
                curr_price = row['close']
                
                # 判定該股在 yfinance 裡是屬於哪個市場
                hist_data = None
                if f"{sid}.TW" in hist.columns and not hist[f"{sid}.TW"].dropna().empty:
                    hist_data = hist[f"{sid}.TW"].dropna()
                elif f"{sid}.TWO" in hist.columns and not hist[f"{sid}.TWO"].dropna().empty:
                    hist_data = hist[f"{sid}.TWO"].dropna()
                
                # 計算 MA5
                if hist_data is not None:
                    # 取得歷史最後 4 筆收盤價
                    past_4_closes = hist_data.tail(4).tolist()
                    if len(past_4_closes) >= 4:
                        # MA5 = (今日價 + 過去四日收盤) / 5
                        ma5 = (sum(past_4_closes) + curr_price) / 5.0
                        status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
                    else:
                        status_str = "歷史資料不足"
                        ma5 = None
                else:
                    status_str = "資料不足 (yf 抓不到)"
                    ma5 = None
                
                results.append({
                    "代號": sid,
                    "名稱": row.get('stock_name', ''),
                    "目前價": curr_price,
                    "五日均價": round(ma5, 2) if ma5 else None,
                    "狀態": status_str,
                    "成交值(百萬)": round(row['amount_m'], 1)
                })
            
            status.update(label="分析完成！", state="complete")
            return pd.DataFrame(results), "成功"
            
    except Exception:
        return None, traceback.format_exc()

# =========================
# 網頁 UI
# =========================
st.title("📈 台股成交值前 300 名 - MA5 強勢股監控 (yfinance)")

with st.sidebar:
    st.header("⚙️ 設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 重新分析數據"):
        st.rerun()

if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("錯誤：找不到 全台股股票.txt")
    stock_ids = []

data, msg = get_ma5_by_yfinance(token, stock_ids)

if data is not None:
    # 統計指標
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = above + below
    
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("樣本總計", f"{total} 檔")

    st.divider()
    st.subheader("前 300 名分析清單")
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.error("分析執行失敗：")
    st.code(msg)

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

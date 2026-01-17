import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股 MA5 強勢股監控 (全市場版)", layout="wide")

def get_ma5_analysis(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取即時快照決定前 300 名
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "API 未回傳數據，請檢查 Token。"
        
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        
        for c in ['close', 'high', 'low', vol_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low', vol_col])
        
        # 計算成交值排行
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
        
        # 2. 獲取歷史資料 (改用 FinMind 以確保上市櫃都能抓到)
        st.info("正在計算 300 檔個股之五日均線...")
        
        # 計算起訖日 (抓過去 15 天確保有足夠交易日)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d')
        
        # 建立結果清單
        results = []
        top_ids = top_300['stock_id'].tolist()
        
        # 為了效能，分批抓取歷史資料 (每 50 檔一批)
        chunk_size = 50
        all_hist = []
        for i in range(0, len(top_ids), chunk_size):
            chunk = top_ids[i:i + chunk_size]
            # 獲取這批股票的日成交資料
            batch_hist = api.taiwan_stock_daily(stock_id=chunk, start_date=start_date, end_date=end_date)
            if not batch_hist.empty:
                all_hist.append(batch_hist)
        
        if not all_hist:
            return None, "無法獲取歷史資料進行 MA5 計算。"
            
        full_hist = pd.concat(all_hist)
        
        # 3. 逐一比對
        for _, row in top_300.iterrows():
            sid = row['stock_id']
            curr_price = row['close']
            
            # 取得該股歷史收盤 (排除今日)
            s_hist = full_hist[full_hist['stock_id'] == sid].sort_values('date')
            # 為了避免重複算到今天的 snapshot，我們拿歷史資料最後四筆 + 當前價
            past_closes = s_hist['close'].tail(4).tolist()
            
            if len(past_closes) >= 4:
                ma5 = (sum(past_closes) + curr_price) / 5.0
                status = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
            else:
                status = "資料不足"
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
st.title("📈 成交值前 300 名 - MA5 強勢股監控 (修正版)")

with st.sidebar:
    st.header("⚙️ 設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 刷新分析數據"):
        st.rerun()

if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

data, msg = get_ma5_analysis(token, stock_ids)

if data is not None:
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = above + below
    
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("樣本總數", f"{total} 檔")

    st.divider()
    st.subheader("前 300 名分析明細 (支援上市櫃)")
    st.dataframe(data, use_container_width=True)
else:
    st.error("分析執行失敗，請將以下錯誤訊息提供給開發人員：")
    st.code(msg)

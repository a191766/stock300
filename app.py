import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback
import time

# ==========================================
# 核心設定區 (您要求的 Token 已放在這裡)
# ==========================================
VERSION = "V11.0 (Token 驗證版)"
API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk"

st.set_page_config(page_title=f"MA5 分析 {VERSION}", layout="wide")

# =========================
# 診斷與 API 登入
# =========================
def check_api_auth(token):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        # 嘗試抓取一個簡單數據測試連線
        test_df = api.taiwan_stock_tick_snapshot()
        if test_df is not None and not test_df.empty:
            return True, "API 登入成功且數據存取正常"
        return False, "API 登入成功但未回傳數據"
    except Exception as e:
        return False, f"API 登入失敗: {str(e)}"

# =========================
# MA5 計算邏輯
# =========================
def get_ma5_v11(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取快照
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "快照數據獲取失敗"
        
        df_snap['stock_id'] = df_snap['stock_id'].astype(str)
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        
        # 數值轉換與成交值計算 (TP 邏輯)
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
            status_text.write(f"📊 正在處理第 {i+1}/300 檔: {sid}")
            
            hist_close = None
            # 嘗試上市與上櫃後綴
            for suffix in [".TW", ".TWO"]:
                try:
                    # 使用單兵抓取模式，這是您測試過可以抓到的邏輯
                    ticker = yf.Ticker(f"{sid}{suffix}")
                    tmp_df = ticker.history(period="1mo")
                    if not tmp_df.empty:
                        # 處理可能的欄位遺失或多層索引
                        if 'Close' in tmp_df.columns:
                            hist_close = tmp_df['Close'].dropna()
                            if not hist_close.empty:
                                break
                except:
                    continue
            
            # 3. 計算 MA5 (今日價 + 前四日收盤) / 5
            if hist_close is not None and len(hist_close) >= 4:
                past_4 = hist_close.tail(4).tolist()
                ma5 = (sum(past_4) + curr_price) / 5.0
                status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
            else:
                ma5 = None
                status_str = "資料不足 (Yahoo 未回傳)"
                
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
    except Exception:
        return None, traceback.format_exc()

# =========================
# UI 呈現
# =========================
st.markdown(f"<h1 style='color: #1E90FF;'>📈 台股 MA5 強勢監控 {VERSION}</h1>", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 API 驗證")
    is_ok, msg = check_api_auth(API_TOKEN)
    if is_ok:
        st.success(f"🟢 {msg}")
    else:
        st.error(f"🔴 {msg}")
    
    st.divider()
    st.header("📂 檔案檢查")
    if os.path.exists("全台股股票.txt"):
        st.success("✅ 找到股票清單檔案")
        with open("全台股股票.txt", "r", encoding="utf-8") as f:
            stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
    else:
        st.error("❌ 找不到 全台股股票.txt")
        stock_ids = []

    st.divider()
    if st.button("🚀 開始執行全市場分析"):
        st.rerun()

# 執行分析
if stock_ids:
    try:
        data, log_msg = get_ma5_v11(API_TOKEN, stock_ids)
        
        if data is not None:
            above = len(data[data['狀態'] == "站上 MA5"])
            below = len(data[data['狀態'] == "跌破 MA5"])
            total = len(data)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("站上 MA5", f"{above} 檔", f"{above/total:.1%}")
            c2.metric("跌破 MA5", f"{below} 檔", f"-{below/total:.1%}", delta_color="inverse")
            c3.metric("有效樣本", f"{total} 檔")
            
            st.divider()
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.error("分析過程發生錯誤")
            st.code(log_msg)
    except Exception:
        st.error("💣 系統崩潰，偵錯日誌如下：")
        st.code(traceback.format_exc())

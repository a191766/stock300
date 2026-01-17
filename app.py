import streamlit as st
import pandas as pd
import yfinance as yf
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback
import time

# ==========================================
# V13.0 版本看板
# ==========================================
VERSION = "V13.0 (救援與診斷對齊版)"
CHANGELOG = """
1. 針對 1/17 (週六) 強化補位邏輯。
2. 增加單一股票抓取診斷，顯示詳細報錯訊息。
3. 修正 yfinance 資料提取結構，防止 DataFrame 錯誤。
"""

st.set_page_config(page_title=f"MA5 分析 {VERSION}", layout="wide")

# 強制版本顯示 (頂端)
st.markdown(f"""
    <div style='background-color: #004d99; padding: 10px; border-radius: 5px;'>
        <h2 style='color: white; margin: 0; text-align: center;'>🚀 目前執行版本：{VERSION}</h2>
    </div>
""", unsafe_allow_html=True)

# =========================
# 核心抓取函式
# =========================
def get_ma5_v13(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取快照
        df_snap = api.taiwan_stock_tick_snapshot()
        if df_snap is None or df_snap.empty:
            return None, "FinMind 快照抓取失敗，請檢查 Token。"
        
        df_snap['stock_id'] = df_snap['stock_id'].astype(str)
        df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
        
        # 計算成交值排行
        v_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
        for c in ['close', 'high', 'low', v_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low', v_col])
        
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[v_col]) / 1_000_000.0
        top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()

        # 2. 逐一抓取 yfinance
        results = []
        p_bar = st.progress(0)
        status_txt = st.empty()
        
        for i, (idx, row) in enumerate(top_300.iterrows()):
            sid = row['stock_id']
            curr_price = row['close']
            status_txt.text(f"分析中 ({i+1}/300): {sid}...")
            
            hist_close = None
            diag_info = "未知原因"
            
            # 嘗試 .TW 與 .TWO
            for suffix in [".TW", ".TWO"]:
                try:
                    # 使用 Ticker 模式下載 1 個月資料
                    ticker_obj = yf.Ticker(f"{sid}{suffix}")
                    # 抓取歷史 (關閉自動調整避免價格不對)
                    tmp_h = ticker_obj.history(period="1mo", auto_adjust=False)
                    if not tmp_h.empty:
                        hist_close = tmp_h['Close'].dropna()
                        break
                    else:
                        diag_info = f"Yahoo 回傳空值 ({sid}{suffix})"
                except Exception as e:
                    diag_info = str(e)
            
            # 3. MA5 計算邏輯 (今日價 + 前四日收盤)
            if hist_close is not None:
                # 剔除歷史資料中可能已經包含的今日(避免重複計算)
                hist_list = hist_close.tolist()
                today_str = datetime.now().strftime('%Y-%m-%d')
                last_date_str = hist_close.index[-1].strftime('%Y-%m-%d')
                
                if last_date_str == today_str:
                    # 如果 yf 已經包含今天，直接取最後 5 筆
                    final_prices = hist_list[-5:]
                else:
                    # 如果 yf 只有到昨天，補上今日快照價格
                    final_prices = (hist_list + [curr_price])[-5:]
                
                if len(final_prices) >= 5:
                    ma5_val = sum(final_prices) / 5.0
                    status_str = "站上 MA5" if curr_price >= ma5_val else "跌破 MA5"
                else:
                    ma5_val = None
                    status_str = f"歷史天數不足 ({len(final_prices)}天)"
            else:
                ma5_val = None
                status_str = f"資料不足 ({diag_info})"
            
            results.append({
                "代號": sid,
                "名稱": row.get('stock_name', ''),
                "目前價": curr_price,
                "五日均價": round(ma5_val, 2) if ma5_val else None,
                "狀態": status_str,
                "成交值(百萬)": round(row['amount_m'], 1)
            })
            p_bar.progress((i + 1) / len(top_300))
            
        status_txt.empty()
        return pd.DataFrame(results), "成功"
    except Exception:
        return None, traceback.format_exc()

# =========================
# UI 配置
# =========================
with st.sidebar:
    st.header("📋 版本監控")
    st.info(f"版本：{VERSION}")
    with st.expander("更新日誌"):
        st.write(CHANGELOG)
    
    if st.button("🧹 清除所有快取並重新載入"):
        st.cache_data.clear()
        st.rerun()

# 檔案讀取
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

# 執行分析
if st.button("🚀 開始分析前 300 名成交值個股", type="primary"):
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk"
    data, log = get_ma5_v13(token, stock_ids)
    
    if data is not None:
        c1, c2, c3 = st.columns(3)
        up = len(data[data['狀態'] == "站上 MA5"])
        down = len(data[data['狀態'] == "跌破 MA5"])
        c1.metric("站上 MA5", f"{up} 檔")
        c2.metric("跌破 MA5", f"{down} 檔")
        c3.metric("有效樣本", len(data))
        
        st.divider()
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.error("💣 程式發生崩潰，請將下方代碼複製給開發人員：")
        st.code(log)

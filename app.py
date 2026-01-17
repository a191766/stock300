import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股成交值分析 (穩定對齊版)", layout="wide")

def get_snapshot_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        
        if df is None or df.empty:
            return None, "API 未回傳數據"
        
        # 1. 基礎清洗：篩選清單內的股票並重設索引
        df = df[df['stock_id'].isin(stock_list)].copy()
        
        # 2. 自動識別成交量欄位
        vol_col = next((c for c in ['total_volume', 'volume', 'Vol'] if c in df.columns), None)
        if not vol_col:
            return None, "找不到成交量相關欄位"

        # 3. 強制數值轉換 (這是防止錯誤的關鍵)
        # 包含：收盤、最高、最低、漲跌價、成交量
        cols_to_fix = ['close', 'high', 'low', 'change_price', vol_col]
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        # 4. 剔除資料不全的標的 (例如當天尚未有成交價或高低價的個股)
        df = df.dropna(subset=['close', 'high', 'low', 'change_price', vol_col])

        # 5. 回推昨日收盤價 (判斷漲跌的基準)
        # 依照您的邏輯：收盤價 - 漲跌價 = 昨收參考價
        df['last_close'] = df['close'] - df['change_price']
        
        # 6. 計算典型價格與成交值 (與您的 0+1.py 同步)
        # TP = (H + L + C) / 3
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        # 成交金額(百萬) = (TP * 成交量) / 1,000,000
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        
        # 7. 排序並取前 300 名
        df = df.sort_values('amount_m', ascending=False).head(300)
        
        # 8. 判定漲跌狀態 (加入微小誤差容忍值 0.001)
        def judge_status(row):
            diff = row['close'] - row['last_close']
            if abs(diff) < 0.001: return "平盤"
            return "上漲" if diff > 0 else "下跌"
        
        df['status'] = df.apply(judge_status, axis=1)
        
        return df, "成功"
    except Exception as e:
        return None, f"程式執行異常: {str(e)}\n{traceback.format_exc()}"

# =========================
# 網頁顯示邏輯
# =========================
st.title("📊 台股成交值前 300 名分析 (穩定對齊版)")

with st.sidebar:
    st.header("⚙️ 設定")
    fm_token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 刷新數據"):
        st.rerun()

# 讀取股票清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    stock_ids = []

# 執行核心分析
data, status_msg = get_snapshot_data(fm_token, stock_ids)

if data is not None:
    # 統計數據
    up = len(data[data['status'] == "上漲"])
    down = len(data[data['status'] == "下跌"])
    even = len(data[data['status'] == "平盤"])
    total = len(data)
    
    # 指標顯示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}" if total > 0 else "0%")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔")
    ratio = up/down if down > 0 else 0
    c4.metric("漲跌比", f"{ratio:.2f}")

    st.divider()

    # 詳細清單
    st.subheader("前 10 名成交值明細 (判斷基準：相對於昨日收盤價)")
    display_df = data[['stock_id', 'stock_name', 'close', 'last_close', 'change_price', 'status', 'amount_m']].copy()
    display_df.columns = ['代號', '名稱', '當前價', '昨日收盤', '漲跌價', '狀態', '成交值(百萬)']
    st.table(display_df.head(10))

    with st.expander("查看前 300 名完整分析資料"):
        st.dataframe(data)
else:
    st.error(status_msg)

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

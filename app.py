import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import yfinance as yf
import os
import sys
import traceback
import requests
from pathlib import Path

# =========================
# 頁面配置 (必須在最前面)
# =========================
st.set_page_config(page_title="台股即時成交值監控", layout="wide")

# =========================
# 核心邏輯區 (保留原功能)
# =========================
def send_line_message(token, message):
    if not token: return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": "Bearer " + token}
    try:
        requests.post(url, headers=headers, data={'message': message})
    except: pass

def get_snapshot_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        if df is None or df.empty: return None
        
        # 篩選並計算成交值
        df = df[df['stock_id'].isin(stock_list)].copy()
        vol_col = 'total_volume' if 'total_volume' in df.columns else 'volume'
        df['amount_m'] = (df['close'] * df[vol_col]) / 1_000_000
        df = df.sort_values('amount_m', ascending=False).head(300)
        return df
    except Exception as e:
        st.error(f"資料獲取失敗: {e}")
        return None

# =========================
# Streamlit 網頁介面
# =========================
st.title("📊 台股成交值前 300 名即時分析")

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 系統設定")
    fm_token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    line_token = st.text_input("LINE Notify Token", value="", type="password")
    
    st.divider()
    if st.button("🔄 立即重新整理"):
        st.rerun()

# 讀取股票清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.warning("找不到 全台股股票.txt，改用預設清單測試。")
    stock_ids = ["2330", "2317", "2454", "2603"]

# 執行分析
data = get_snapshot_data(fm_token, stock_ids)

if data is not None:
    # 統計數據
    up = len(data[data['change_price'] > 0])
    down = len(data[data['change_price'] < 0])
    even = len(data[data['change_price'] == 0])
    total = len(data)
    
    # 第一列：數據指標
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}", delta_color="normal")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔", "0%")
    ratio = up/down if down != 0 else 0
    c4.metric("漲跌比 (漲/跌)", f"{ratio:.2f}")

    st.divider()

    # 第二列：圖表與明細
    left_col, right_col = st.columns([1, 2])
    
    with left_col:
        st.subheader("漲跌比例圖")
        fig = go.Figure(data=[go.Pie(
            labels=['上漲', '下跌', '平盤'],
            values=[up, down, even],
            hole=.4,
            marker_colors=['#FF4B4B', '#00CC96', '#636EFA']
        )])
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    with right_col:
        st.subheader("成交值 Top 10 明細")
        display_df = data[['stock_id', 'stock_name', 'close', 'change_rate', 'amount_m']].copy()
        display_df.columns = ['代號', '名稱', '價格', '漲跌幅%', '成交金額(百萬)']
        st.dataframe(display_df.head(10), use_container_width=True)

    # 第三列：完整清單
    with st.expander("點擊展開前 300 名完整清單"):
        st.dataframe(data, use_container_width=True)

    # 自動推送 LINE (可選)
    if st.checkbox("自動推送當前結果至 LINE"):
        msg = f"\n即時分析({datetime.now().strftime('%H:%M')})\n漲:{up} / 跌:{down}\n漲跌比:{ratio:.2f}"
        send_line_message(line_token, msg)
        st.success("已發送至 LINE")

else:
    st.info("目前非交易時間或無法取得即時資料。")

# 保持最後提示
st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
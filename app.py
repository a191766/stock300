import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from FinMind.data import DataLoader
from datetime import datetime
import os
import requests
import traceback

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股成交值分析 - 同步穩定版", layout="wide")

def get_snapshot_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        
        if df is None or df.empty:
            return None, "API 未回傳數據"
        
        # 1. 確保 stock_id 存在 (有時在 index 有時在 column)
        df = df.reset_index()
        
        # 2. 篩選名單
        df = df[df['stock_id'].isin(stock_list)].copy()
        
        # 3. 自動偵測成交量欄位 (對應不同版本的 API)
        vol_col = next((c for c in ['total_volume', 'volume', 'Vol'] if c in df.columns), None)
        if not vol_col:
            return None, f"找不到成交量欄位，現有欄位: {list(df.columns)}"

        # 4. 強制轉為數值格式並處理缺失值
        cols_to_fix = ['close', 'high', 'low', 'change_price', vol_col]
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 剔除無法計算的資料 (同步您的 0+1.py 邏輯)
        df = df.dropna(subset=['close', 'high', 'low', vol_col])

        # 5. 完全同步 0+1.py 的 Typical Price 邏輯
        # TP = (最高 + 最低 + 收盤) / 3
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        
        # 成交金額(百萬) = (TP * 成交股數) / 1,000,000
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        
        # 6. 排序並取前 300 名 (這決定了統計的分母)
        df = df.sort_values('amount_m', ascending=False).head(300)
        return df, vol_col
    except Exception as e:
        err_msg = f"運算錯誤: {str(e)}\n{traceback.format_exc()}"
        return None, err_msg

# =========================
# 網頁顯示
# =========================
st.title("📊 台股成交值前 300 名分析 (同步邏輯版)")

# 側邊欄
with st.sidebar:
    st.header("⚙️ 系統設定")
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

# 抓取數據
data, status = get_snapshot_data(fm_token, stock_ids)

if data is not None:
    # 統計漲跌
    up = len(data[data['change_price'] > 0])
    down = len(data[data['change_price'] < 0])
    even = len(data[data['change_price'] == 0])
    total = len(data)
    
    # 儀表板數據
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}" if total > 0 else "0%")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔")
    ratio = up/down if down != 0 else (up if down == 0 else 0)
    c4.metric("漲跌比", f"{ratio:.2f}")

    st.divider()

    # 清單表格 (防 KeyError 版)
    st.subheader("前 10 名成交值明細")
    # 定義想要顯示的理想欄位
    ideal_cols = {
        'stock_id': '代號',
        'stock_name': '名稱',
        'close': '收盤價',
        'change_price': '漲跌',
        'amount_m': '成交值(百萬)'
    }
    # 只選取目前資料中確實存在的欄位
    actual_cols = [c for c in ideal_cols.keys() if c in data.columns]
    display_df = data[actual_cols].copy()
    display_df.rename(columns={c: ideal_cols[c] for c in actual_cols}, inplace=True)
    
    st.table(display_df.head(10))

    with st.expander("查看前 300 名完整計算資料"):
        st.dataframe(data)

else:
    st.error(f"無法載入分析內容：\n{status}")

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

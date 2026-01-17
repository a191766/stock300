import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from FinMind.data import DataLoader
from datetime import datetime
import os
import requests

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股即時成交值監控 (同步防錯版)", layout="wide")

def get_snapshot_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        
        if df is None or df.empty:
            st.warning("API 未回傳任何數據。")
            return None
        
        # 1. 篩選名單
        df = df[df['stock_id'].isin(stock_list)].copy()
        
        # 2. 自動偵測成交量欄位 (防止 KeyError)
        # 某些版本叫 total_volume，某些叫 volume
        vol_col = None
        for v in ['total_volume', 'volume', 'Vol']:
            if v in df.columns:
                vol_col = v
                break
        
        if not vol_col:
            st.error(f"找不到成交量欄位，現有欄位為: {list(df.columns)}")
            return None

        # 3. 強制轉為數值格式，避免運算錯誤
        calc_cols = ['close', 'high', 'low', 'change_price', vol_col]
        for col in calc_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 排除數值缺失的資料
        df = df.dropna(subset=['close', 'high', 'low', vol_col])

        # 4. 同步您的 0+1.py 邏輯：使用 Typical Price (H+L+C)/3
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        
        # 5. 計算成交金額 (百萬) -> TP * 成交股數 / 1,000,000
        df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
        
        # 6. 排序並取前 300 名
        df = df.sort_values('amount_m', ascending=False).head(300)
        return df, vol_col
    except Exception as e:
        st.error(f"發生錯誤: {e}")
        st.code(traceback.format_exc())
        return None, None

# =========================
# Streamlit 網頁介面
# =========================
st.title("📊 台股成交值前 300 名分析 (同步邏輯版)")

with st.sidebar:
    st.header("⚙️ 設定")
    fm_token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 手動更新數據"):
        st.rerun()

# 讀取股票清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        # 確保讀取為字串清單
        stock_ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt 檔案！")
    stock_ids = []

result = get_snapshot_data(fm_token, stock_ids)

if result and result[0] is not None:
    data, v_col = result
    
    # 統計漲跌 (使用 change_price 判斷)
    up = len(data[data['change_price'] > 0])
    down = len(data[data['change_price'] < 0])
    even = len(data[data['change_price'] == 0])
    total = len(data)
    
    # 指標顯示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲家數", f"{up} 檔", f"{up/total:.1%}" if total > 0 else "0%")
    c2.metric("下跌家數", f"{down} 檔", f"-{down/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("平盤家數", f"{even} 檔")
    ratio = up/down if down != 0 else (up if down == 0 else 0)
    c4.metric("漲跌比", f"{ratio:.2f}")

    st.divider()

    # 表格顯示 (與您的 CSV 欄位名稱靠攏)
    st.subheader(f"前 10 名成交值明細 (成交量欄位: {v_col})")
    res_df = data[['stock_id', 'stock_name', 'close', 'change_price', 'amount_m']].copy()
    res_df.columns = ['代號', '名稱', '收盤價', '漲跌', '成交值(百萬)']
    st.table(res_df.head(10))

    # 完整清單
    with st.expander("展開前 300 名完整分析清單"):
        st.write(data)
else:
    st.info("等待資料載入中... 若長時間沒反應請檢查側邊欄 Token。")

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

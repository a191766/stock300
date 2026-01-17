import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime
import os
import traceback

# 配置頁面
st.set_page_config(page_title="台股成交值 300 名監控", layout="wide")

def get_data(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        df = api.taiwan_stock_tick_snapshot()
        if df is None or df.empty: return None, "API 無回傳"

        # 重整索引並篩選
        df = df.reset_index()
        df = df[df['stock_id'].isin(stock_list)].copy()

        # 1. 偵測成交量欄位
        v_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), None)
        if not v_col: return None, "找不到成交量欄位"

        # 2. 強制轉為數值
        for c in ['close', 'high', 'low', 'change_price', v_col]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        
        # 3. 剔除空值
        df = df.dropna(subset=['close', 'high', 'low', 'change_price', v_col])

        # 4. 計算與原始程式一致的數據
        df['last_close'] = df['close'] - df['change_price'] # 回推昨收
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['amount_m'] = (df['tp'] * df[v_col]) / 1_000_000.0

        # 5. 排序前 300 名
        df = df.sort_values('amount_m', ascending=False).head(300)

        # 6. 判定漲跌 (同步您的判斷邏輯)
        def judge(row):
            if row['change_price'] > 0: return "漲"
            if row['change_price'] < 0: return "跌"
            return "平"
        df['status'] = df.apply(judge, axis=1)

        return df, "成功"
    except Exception:
        return None, traceback.format_exc()

st.title("📊 台股成交值前 300 名即時分析")

# 側邊欄
with st.sidebar:
    st.header("⚙️ 設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 刷新數據"): st.rerun()

# 讀取檔案
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        ids = [s.strip() for s in f.read().replace("\n", "").split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt")
    ids = []

# 執行與顯示
res, msg = get_data(token, ids)

if res is not None:
    u = len(res[res['status'] == "漲"])
    d = len(res[res['status'] == "跌"])
    e = len(res[res['status'] == "平"])
    total = len(res)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("上漲", f"{u} 檔", f"{u/total:.1%}")
    c2.metric("下跌", f"{d} 檔", f"-{d/total:.1%}", delta_color="inverse")
    c3.metric("平盤", f"{e} 檔")
    c4.metric("漲跌比", f"{u/d:.2f}" if d > 0 else "N/A")

    st.divider()
    st.subheader("成交值前 10 名 (已自動推算昨日收盤價)")
    show_df = res[['stock_id', 'close', 'last_close', 'change_price', 'status', 'amount_m']].head(10)
    show_df.columns = ['代號', '今日價', '昨日收盤', '漲跌價', '狀態', '金額(百萬)']
    st.table(show_df)

    with st.expander("展開完整 300 名數據"):
        st.dataframe(res)
else:
    st.error("分析錯誤，請檢查下方資訊：")
    st.code(msg)

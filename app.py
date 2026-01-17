import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback
import time

# =========================
# 頁面配置
# =========================
st.set_page_config(page_title="台股 MA5 強勢股監控 (穩定分批版)", layout="wide")

def get_ma5_analysis(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取即時快照決定前 300 名
        with st.status("正在獲取市場即時快照...", expanded=True) as status:
            df_snap = api.taiwan_stock_tick_snapshot()
            if df_snap is None or df_snap.empty:
                return None, "API 未回傳快照數據，請檢查 Token 或權限。"
            
            # 強制將代號轉為字串並過濾清單
            df_snap['stock_id'] = df_snap['stock_id'].astype(str)
            df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
            
            vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
            for c in ['close', 'high', 'low', vol_col]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df = df.dropna(subset=['close', 'high', 'low', vol_col])
            
            # 計算成交值排行
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
            df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
            top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
            
            status.update(label=f"已選定成交值前 {len(top_300)} 名標的，開始獲取歷史均線...")

            # 2. 分批獲取歷史資料 (每 30 檔一組，防止 API 逾時)
            top_ids = top_300['stock_id'].tolist()
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=25)).strftime('%Y-%m-%d')
            
            all_hist_list = []
            progress_bar = st.progress(0)
            
            chunk_size = 30
            for i in range(0, len(top_ids), chunk_size):
                chunk = top_ids[i:i + chunk_size]
                try:
                    batch_hist = api.taiwan_stock_daily(stock_id=chunk, start_date=start_date, end_date=end_date)
                    if not batch_hist.empty:
                        all_hist_list.append(batch_hist)
                except:
                    pass
                progress_bar.progress(min((i + chunk_size) / len(top_ids), 1.0))
            
            if not all_hist_list:
                return None, "無法獲取任何歷史資料，請稍後再試。"
                
            full_hist = pd.concat(all_hist_list)
            full_hist['stock_id'] = full_hist['stock_id'].astype(str)
            
            # 3. 逐一計算 MA5
            results = []
            today_str = datetime.now().strftime('%Y-%m-%d')

            for _, row in top_300.iterrows():
                sid = row['stock_id']
                curr_price = row['close']
                
                # 取得該股歷史資料
                s_hist = full_hist[full_hist['stock_id'] == sid].sort_values('date')
                
                if s_hist.empty:
                    results.append({"代號": sid, "名稱": row.get('name', ''), "目前價": curr_price, "五日均價": None, "狀態": "抓不到歷史資料", "成交值(百萬)": round(row['amount_m'], 1)})
                    continue

                hist_closes = s_hist['close'].tolist()
                last_date = s_hist['date'].iloc[-1]
                
                # 日期判定邏輯
                if last_date != today_str:
                    # 如果歷史資料還沒更新今天，手動把今日快照補進去
                    final_prices = (hist_closes + [curr_price])[-5:]
                else:
                    # 如果歷史資料已包含今日，直接取最後 5 筆
                    final_prices = hist_closes[-5:]
                
                if len(final_prices) >= 5:
                    ma5 = sum(final_prices) / 5.0
                    status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
                else:
                    status_str = "資料天數不足"
                    ma5 = None
                
                results.append({
                    "代號": sid,
                    "名稱": row.get('name', row.get('stock_name', '')),
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
# 網頁顯示
# =========================
st.title("📈 成交值前 300 名 - MA5 強勢股監控")

with st.sidebar:
    st.header("⚙️ 設定")
    token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
    if st.button("🔄 重新分析"):
        st.rerun()

# 讀取清單
if os.path.exists("全台股股票.txt"):
    with open("全台股股票.txt", "r", encoding="utf-8") as f:
        # 讀取並轉換為字串列表
        content = f.read().replace("\n", "")
        stock_ids = [s.strip() for s in content.split(",") if s.strip()]
else:
    st.error("找不到 全台股股票.txt，請確認已上傳檔案。")
    stock_ids = []

data, msg = get_ma5_analysis(token, stock_ids)

if data is not None:
    # 統計
    above = len(data[data['狀態'] == "站上 MA5"])
    below = len(data[data['狀態'] == "跌破 MA5"])
    total = len(data)
    
    # 儀表板
    c1, c2, c3 = st.columns(3)
    c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
    c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
    c3.metric("總分析標的數", f"{total} 檔")

    st.divider()

    # 排序：優先看強勢股
    data = data.sort_values(by=["狀態", "成交值(百萬)"], ascending=[True, False])

    st.subheader("前 300 名分析清單")
    st.dataframe(data, use_container_width=True, hide_index=True)
else:
    st.error("分析執行失敗：")
    st.code(msg)

st.sidebar.markdown(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

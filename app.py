import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
from datetime import datetime, timedelta
import os
import traceback
import sys

# =========================
# 頁面配置
# =========================
try:
    st.set_page_config(page_title="台股 MA5 強勢股分析", layout="wide")
except:
    # 防止在非 Streamlit 環境下執行時報錯
    pass

def get_ma5_analysis(token, stock_list):
    try:
        api = DataLoader()
        api.login_by_token(api_token=token)
        
        # 1. 抓取即時快照決定前 300 名
        with st.status("正在抓取市場快照並計算排行...", expanded=True) as status:
            df_snap = api.taiwan_stock_tick_snapshot()
            if df_snap is None or df_snap.empty:
                return None, "API 未回傳快照數據。"
            
            # 強制轉字串與數值清洗
            df_snap['stock_id'] = df_snap['stock_id'].astype(str)
            df = df_snap[df_snap['stock_id'].isin(stock_list)].copy()
            
            # 偵測欄位名稱 (有些版本是 total_volume 有些是 volume)
            vol_col = next((c for c in ['total_volume', 'volume'] if c in df.columns), 'volume')
            for c in ['close', 'high', 'low', vol_col]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            
            # 典型價格 TP = (H+L+C)/3，成交金額 = TP * 量
            df = df.dropna(subset=['close', 'high', 'low', vol_col])
            df['tp'] = (df['high'] + df['low'] + df['close']) / 3.0
            df['amount_m'] = (df['tp'] * df[vol_col]) / 1_000_000.0
            
            top_300 = df.sort_values('amount_m', ascending=False).head(300).copy()
            status.update(label=f"已選定前 {len(top_300)} 檔熱門股，正在同步 MA5 均線...", state="running")

            # 2. 處理時區與日期 (強制使用台灣時間)
            # 考慮到 GitHub 伺服器在國外，手動計算台灣日期
            tw_time = datetime.utcnow() + timedelta(hours=8)
            end_date = tw_time.strftime('%Y-%m-%d')
            start_date = (tw_time - timedelta(days=30)).strftime('%Y-%m-%d') # 拉長到30天確保有足夠交易日
            
            # 3. 分批獲取歷史資料
            top_ids = top_300['stock_id'].tolist()
            all_hist_list = []
            chunk_size = 50
            for i in range(0, len(top_ids), chunk_size):
                chunk = top_ids[i:i + chunk_size]
                batch_hist = api.taiwan_stock_daily(stock_id=chunk, start_date=start_date, end_date=end_date)
                if not batch_hist.empty:
                    all_hist_list.append(batch_hist)
            
            if not all_hist_list:
                return None, "無法獲取歷史資料庫數據，請檢查 Token 是否過期或時段是否正確。"
                
            full_hist = pd.concat(all_hist_list)
            full_hist['stock_id'] = full_hist['stock_id'].astype(str)
            
            # 4. 計算 MA5
            results = []
            today_str = end_date

            for _, row in top_300.iterrows():
                sid = row['stock_id']
                curr_price = row['close']
                sname = row.get('stock_name', row.get('info_name', '未知')) # 修正名稱抓取
                
                # 取得該股歷史資料
                s_hist = full_hist[full_hist['stock_id'] == sid].sort_values('date')
                
                if s_hist.empty:
                    results.append({"代號": sid, "名稱": sname, "目前價": curr_price, "五日均價": None, "狀態": "資料不足", "成交值(百萬)": round(row['amount_m'], 1)})
                    continue

                hist_closes = s_hist['close'].tolist()
                hist_dates = s_hist['date'].tolist()
                
                # 如果歷史資料最後一天不是今天，則補上今日 Snapshot 價格
                if hist_dates[-1] != today_str:
                    final_prices = (hist_closes + [curr_price])[-5:]
                else:
                    final_prices = hist_closes[-5:]
                
                if len(final_prices) >= 5:
                    ma5 = sum(final_prices) / 5.0
                    status_str = "站上 MA5" if curr_price >= ma5 else "跌破 MA5"
                else:
                    status_str = "資料不足"
                    ma5 = None
                
                results.append({
                    "代號": sid,
                    "名稱": sname,
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
# 主程式邏輯
# =========================
def main():
    st.title("📈 台股成交值前 300 名 - MA5 強勢股分析")

    with st.sidebar:
        st.header("⚙️ 系統設定")
        # 預設使用您的 Token
        token = st.text_input("FinMind Token", value="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMS0xNCAxOTowMDowNiIsInVzZXJfaWQiOiJcdTllYzNcdTRlYzFcdTVhMDEiLCJlbWFpbCI6ImExOTE3NjZAZ21haWwuY29tIiwiaXAiOiIifQ.JFPtMDNbxKzhl8HsxkOlA1tMlwq8y_NA6NpbRel6HCk", type="password")
        if st.button("🔄 重新執行分析"):
            st.rerun()

    # 讀取股票清單
    if os.path.exists("全台股股票.txt"):
        with open("全台股股票.txt", "r", encoding="utf-8") as f:
            content = f.read().strip()
            # 支援逗號或換行分割
            stock_ids = [s.strip() for s in content.replace("\n", ",").split(",") if s.strip()]
    else:
        st.error("錯誤：找不到 全台股股票.txt，請確認檔案是否已上傳至 GitHub。")
        stock_ids = []

    if stock_ids:
        data, msg = get_ma5_analysis(token, stock_ids)

        if data is not None:
            # 頂部指標
            above = len(data[data['狀態'] == "站上 MA5"])
            below = len(data[data['狀態'] == "跌破 MA5"])
            total = len(data)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("站上 MA5 (強勢)", f"{above} 檔", f"{above/total:.1%}" if total > 0 else "0%")
            c2.metric("跌破 MA5 (弱勢)", f"{below} 檔", f"-{below/total:.1%}" if total > 0 else "0%", delta_color="inverse")
            c3.metric("總計分析數", f"{total} 檔")

            st.divider()

            # 顯示表格
            st.subheader("分析明細")
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.error("分析執行失敗：")
            st.code(msg)

    st.sidebar.markdown(f"最後更新 (TW)：{(datetime.utcnow() + timedelta(hours=8)).strftime('%H:%M:%S')}")

if __name__ == "__main__":
    try:
        # 如果是在 Streamlit 環境中
        if 'streamlit' in sys.modules or any('streamlit' in arg for arg in sys.argv):
            main()
        else:
            # 如果是純 Python 執行 (雙擊)
            print("正在啟動 Streamlit 服務... 請稍後")
            os.system(f"streamlit run {sys.argv[0]}")
    except Exception as e:
        print(f"程式執行發生錯誤: {e}")
        traceback.print_exc()
    finally:
        # 依照要求：不論成功失敗，都要等按下 Enter 才能結束
        if not ('streamlit' in sys.modules):
            input("\n程式執行完畢，請按下 Enter 鍵結束...")

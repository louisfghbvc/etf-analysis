import urllib.request
import ssl
import re
import json
import os
import subprocess
import time
from datetime import datetime

# --- 設定 ---
ETF_TICKERS = ["00981A", "00992A"]  
DATA_DIR = "/home/louisfghbvc/.openclaw/workspace/apps/etf-analysis/data"
os.makedirs(DATA_DIR, exist_ok=True)

# 由於投信官網通常有強力防護，我們暫時使用穩定性較高的 MoneyDJ 作為 MVP
# （若日後有 OpenClaw Browser 工具完整授權，可改寫為無頭瀏覽器抓取投信官網 50 檔）

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}

def _fetch_etf_holdings_cmoney_old(etf_id):
    """從 CMoney (理財寶) 使用 Puppeteer 無頭瀏覽器抓取完整 50 檔成分股"""
    print(f"正在透過無頭瀏覽器抓取 {etf_id} 的完整持股明細...")
    import subprocess
    import json
    
    # 指向剛才寫好的 Node.js 爬蟲腳本
    script_path = "/home/louisfghbvc/.openclaw/workspace/scripts/etf_tracker/crawler.js"
    cmd = ["node", script_path, etf_id]
    
    try:
        # 注意: 這裡設定 working directory 到 /tmp 是因為裡面裝了 puppeteer-core
        result = subprocess.run(cmd, cwd="/tmp", capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"⚠️ Node.js 爬蟲回報錯誤: {result.stderr}")
            return None
            
        # 尋找輸出中的 JSON 字串 (過濾掉前面的 console.log)
        output_lines = result.stdout.strip().split('\n')
        json_str = ""
        for line in output_lines:
            if line.startswith("{") and line.endswith("}"):
                json_str = line
                break
                
        if not json_str:
            print(f"⚠️ {etf_id}: 找不到輸出的 JSON！")
            return None
            
        holdings = json.loads(json_str)
        print(f"✅ {etf_id}: 成功抓取 {len(holdings)} 檔完整成分股！")
        return holdings
        
    except Exception as e:
        print(f"❌ {etf_id} 抓取失敗: {e}")
        return None



def fetch_etf_holdings_moneydj(etf_id):
    """從 MoneyDJ 爬取 ETF 持股明細 (前十大)"""
    import urllib.request
    url = f"https://www.moneydj.com/ETF/X/Basic/Basic0007.xdjhtm?etfid={etf_id}.TW"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx) as res:
            html = res.read().decode('utf-8')
        import re
        tables = re.findall(r'<table(.*?)>(.*?)</table>', html, re.DOTALL)
        target_table = None
        for attrs, content in tables:
            if "個股名稱" in content and "持有股數" in content:
                target_table = content
                break
        if not target_table: return None
        rows = re.findall(r'<tr.*?>(.*?)</tr>', target_table, re.DOTALL)
        holdings = {}
        for r in rows[1:]:
            cells = re.findall(r'<t[dh].*?>(.*?)</t[dh]>', r, re.DOTALL)
            clean_cells = [re.sub(r'<.*?>', '', c).strip().replace('&nbsp;', '').replace('\n', '').replace('\r', '') for c in cells]
            if len(clean_cells) >= 3:
                raw_name = clean_cells[0]
                match = re.match(r'(.*?)\((.*?)\.TW\)', raw_name)
                if match:
                    name = match.group(1).strip()
                    ticker = match.group(2).strip()
                else:
                    match = re.search(r'\((.*?)\.', raw_name)
                    ticker = match.group(1).strip() if match else raw_name
                    name = re.sub(r'\(.*?\)', '', raw_name).strip()
                weight = float(clean_cells[1].replace(',', ''))
                shares = float(clean_cells[2].replace(',', ''))
                holdings[ticker] = {"name": name, "weight": weight, "shares": shares}
        print(f"✅ {etf_id}: MoneyDJ 降級抓取 {len(holdings)} 檔成分股！")
        return holdings
    except Exception as e:
        print(f"❌ MoneyDJ 抓取失敗: {e}")
        return None


def fetch_etf_holdings_fallback(etf_id):
    """自動降級機制: 先試 CMoney (50檔)，若超時或失敗則降級 MoneyDJ (10檔)"""
    # 1. 嘗試 CMoney
    print(f"正在透過無頭瀏覽器抓取 {etf_id} 的完整持股明細...")
    import subprocess
    import json
    script_path = "/home/louisfghbvc/.openclaw/workspace/scripts/etf_tracker/crawler.js"
    cmd = ["node", script_path, etf_id]
    
    try:
        # 給 30 秒 Timeout
        result = subprocess.run(cmd, cwd="/tmp", capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines:
                if line.startswith("{") and line.endswith("}"):
                    holdings = json.loads(line)
                    if len(holdings) > 10:
                        print(f"✅ {etf_id}: CMoney 成功抓取 {len(holdings)} 檔完整成分股！")
                        return holdings
    except subprocess.TimeoutExpired:
        print(f"⚠️ CMoney 無頭瀏覽器抓取超時！")
    except Exception as e:
        print(f"⚠️ CMoney 抓取錯誤: {e}")
        
    # 2. 降級 MoneyDJ
    print(f"⚠️ {etf_id} 啟動降級機制 -> 抓取 MoneyDJ 前十大持股...")
    return fetch_etf_holdings_moneydj(etf_id)

def fetch_all_prices():
    """從 TWSE (上市) 和 TPEx (上櫃) OpenAPI 抓取今日全市場收盤價"""
    print("📡 正在抓取全市場上市櫃收盤價 (計算投信建倉成本用)...")
    price_dict = {}
    
    # 1. 抓取上市 (TWSE)
    twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        req = urllib.request.Request(twse_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            for item in data:
                price_str = item.get('ClosingPrice', '').strip()
                if price_str and price_str not in ['---', '----']:
                    try:
                        price_dict[item['Code']] = float(price_str.replace(',', ''))
                    except ValueError:
                        pass
        print(f"✅ 成功載入上市股票收盤價")
    except Exception as e:
        print(f"❌ TWSE 收盤價抓取失敗: {e}")

    # 2. 抓取上櫃 (TPEx)
    tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
    try:
        req = urllib.request.Request(tpex_url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            for item in data:
                price_str = item.get('Close', '').strip()
                if price_str and price_str not in ['---', '----']:
                    try:
                        price_dict[item['SecuritiesCompanyCode']] = float(price_str.replace(',', ''))
                    except ValueError:
                        pass
        print(f"✅ 成功載入上櫃股票收盤價")
    except Exception as e:
        print(f"❌ TPEx 收盤價抓取失敗: {e}")
        
    return price_dict

def find_previous_data(today_str):
    """找出前一天的資料檔案"""
    files = [f for f in os.listdir(DATA_DIR) if f.endswith("_holdings.json") and f < f"{today_str}_holdings.json"]
    if not files:
        return None
    latest = sorted(files)[-1]
    with open(os.path.join(DATA_DIR, latest), "r", encoding="utf-8") as f:
        return json.load(f), latest.split('_')[0]

def diff_holdings(old_data, new_data, etf_id, market_prices):
    """比對 T 日與 T-1 日的差異"""
    old_holdings = old_data.get(etf_id, {})
    new_holdings = new_data.get(etf_id, {})
    
    added = []
    removed = []
    changed = []
    
    for ticker, info in new_holdings.items():
        if ticker not in old_holdings:
            info_copy = info.copy()
            info_copy["ticker"] = ticker
            info_copy["cost_estimate"] = market_prices.get(ticker, 0.0)
            added.append(info_copy)
        else:
            old_info = old_holdings[ticker]
            # 假設股數變動超過 100 股才算是有意義的加減碼 (避免小數點進位誤差)
            diff_shares = info['shares'] - old_info['shares']
            if abs(diff_shares) > 100:
                changed.append({
                    "name": info["name"],
                    "ticker": ticker,
                    "old_shares": old_info["shares"],
                    "new_shares": info["shares"],
                    "diff": diff_shares,
                    "cost_estimate": market_prices.get(ticker, 0.0)
                })
                
    for ticker, old_info in old_holdings.items():
        if ticker not in new_holdings:
            old_info_copy = old_info.copy()
            old_info_copy["ticker"] = ticker
            removed.append(old_info_copy)
            
    return {"added": added, "removed": removed, "changed": changed}


def update_github_pages(diff_dict, today_str, prev_date_str, daily_data):
    HTML_PATH = "/home/louisfghbvc/.openclaw/workspace/apps/etf-analysis/index.html"
    try:
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
            
        match = re.search(r'const HISTORY_DATA = (\[.*?\]);', html, re.DOTALL)
        if not match:
            print("⚠️ 找不到 HISTORY_DATA 變數")
            return
            
        history_data = json.loads(match.group(1))
        
        to_label = f"{today_str[:4]}/{today_str[4:6]}/{today_str[6:]}"
        from_label = f"{prev_date_str[:4]}/{prev_date_str[4:6]}/{prev_date_str[6:]}"
        
        for etf_id, diff in diff_dict.items():
            if not diff["added"] and not diff["removed"] and not diff["changed"]:
                continue
                
            etf_entry = next((e for e in history_data if e["ticker"] == etf_id), None)
            if not etf_entry:
                continue
                
            new_change = {
                "from_label": from_label,
                "to_label": to_label,
                "added": [{"ticker": item["ticker"], "name": item["name"], "weight": item.get("weight", 0.0), "shares": item["shares"], "cost_estimate": item.get("cost_estimate", 0)} for item in diff["added"]],
                "removed": [{"ticker": item["ticker"], "name": item["name"], "weight": item.get("weight", 0.0), "shares": item["shares"]} for item in diff["removed"]],
                "changed": [{"ticker": item["ticker"], "name": item["name"], "from_weight": 0.0, "to_weight": 0.0, "from_shares": item["old_shares"], "to_shares": item["new_shares"], "cost_estimate": item.get("cost_estimate", 0)} for item in diff["changed"]]
            }
            
            etf_entry["changes"].insert(0, new_change)
            etf_entry["changes"] = etf_entry["changes"][:5] # 保留最近5筆
            
        new_json_str = json.dumps(history_data, ensure_ascii=False)
        new_html = html[:match.start(1)] + new_json_str + html[match.end(1):]
        
        # Phase 2: 自動更新 CROSS_DATA (交叉持股排行榜)
        print("🔄 正在計算全自動交叉持股 (CROSS_DATA)...")
        match_cards = re.search(r'const ETF_CARDS\s*=\s*(\[.*?\]);', new_html, re.DOTALL)
        if match_cards:
            etf_cards = json.loads(match_cards.group(1))
            etf_info_map = {card["ticker"]: card for card in etf_cards}
            stock_map = {}
            
            import os
            # 從剛剛存檔的 daily_data 抓出今天的完整名單
            for etf_id, stocks in daily_data.items():
                etf_info = etf_info_map.get(etf_id)
                if not etf_info: continue
                
                # 粗估 AUM
                aum_str = etf_info.get("aum", "100 億")
                aum_num = float(re.search(r'\d+', aum_str).group(0)) if re.search(r'\d+', aum_str) else 100
                
                for ticker, info in stocks.items():
                    if ticker not in stock_map:
                        stock_map[ticker] = {
                            "ticker": ticker,
                            "name": info["name"],
                            "etf_count": 0,
                            "max_weight": 0,
                            "total_capital": 0,
                            "total_shares": 0,
                            "etfs": []
                        }
                    st = stock_map[ticker]
                    st["etf_count"] += 1
                    st["max_weight"] = max(st["max_weight"], info["weight"])
                    st["total_shares"] += info["shares"]
                    
                    capital_yi = round(aum_num * (info["weight"] / 100), 1)
                    st["total_capital"] = round(st["total_capital"] + capital_yi, 1)
                    
                    st["etfs"].append({
                        "etf_ticker": etf_id,
                        "etf_name": etf_info["name"],
                        "color": etf_info.get("color", "#34d399"),
                        "weight": info["weight"],
                        "capital_yi": capital_yi,
                        "shares": info["shares"]
                    })
            
            cross_data_list = list(stock_map.values())
            # 排序: 被越多家投信買進的排越前面，票數一樣看金額
            cross_data_list.sort(key=lambda x: (x["etf_count"], x["total_capital"]), reverse=True)
            cross_data_list = cross_data_list[:50]
            
            match_cross = re.search(r'const CROSS_DATA\s*=\s*(\[.*?\]);', new_html, re.DOTALL)
            if match_cross:
                new_cross_json = json.dumps(cross_data_list, ensure_ascii=False)
                new_html = new_html[:match_cross.start(1)] + new_cross_json + new_html[match_cross.end(1):]
                print(f"✅ 成功計算出 {len(cross_data_list)} 檔熱門交叉持股！")
                
            # Phase 2: 自動更新 WALL_DATA (動態牆)
            print("🔄 正在產生首頁動態牆 (WALL_DATA)...")
            wall_added = []
            wall_removed = []
            for etf_id, diff in diff_dict.items():
                etf_info = etf_info_map.get(etf_id, {})
                for item in diff["added"]:
                    wall_added.append({
                        "ticker": item["ticker"],
                        "name": item["name"],
                        "etfs": [{
                            "etf_ticker": etf_id,
                            "etf_name": etf_info.get("name", ""),
                            "color": etf_info.get("color", "#34d399"),
                            "shares_zhang": round(item["shares"] / 1000) # 轉成張數
                        }]
                    })
                for item in diff["removed"]:
                    wall_removed.append({
                        "ticker": item["ticker"],
                        "name": item["name"],
                        "etfs": [{
                            "etf_ticker": etf_id,
                            "etf_name": etf_info.get("name", ""),
                            "color": etf_info.get("color", "#34d399"),
                            "shares_zhang": round(item["shares"] / 1000)
                        }]
                    })
                    
            if wall_added or wall_removed:
                wall_entry = {
                    "from_label": f"{prev_date_str[4:6]}/{prev_date_str[6:]}",
                    "to_label": f"{today_str[4:6]}/{today_str[6:]}",
                    "added_stocks": wall_added,
                    "removed_stocks": wall_removed
                }
                
                match_wall = re.search(r'const WALL_DATA\s*=\s*(\[.*?\]);', new_html, re.DOTALL)
                if match_wall:
                    wall_data = json.loads(match_wall.group(1))
                    wall_data.insert(0, wall_entry)
                    wall_data = wall_data[:10] # 保留最近 10 天的動態牆
                    
                    new_wall_json = json.dumps(wall_data, ensure_ascii=False)
                    new_html = new_html[:match_wall.start(1)] + new_wall_json + new_html[match_wall.end(1):]
                    print(f"✅ 成功更新 WALL_DATA 首頁動態牆！")

        
        with open(HTML_PATH, "w", encoding="utf-8") as f:
            f.write(new_html)
            
        print("✅ 成功更新 index.html (HISTORY_DATA)")
        
        # Git Push
        print("🚀 準備推播至 GitHub Pages...")
        import subprocess
        cwd = "/home/louisfghbvc/.openclaw/workspace/apps/etf-analysis"
        subprocess.run(["git", "add", "index.html"], cwd=cwd)
        subprocess.run(["git", "commit", "-m", f"Auto-update ETF history {today_str}"], cwd=cwd)
        subprocess.run(["git", "push"], cwd=cwd)
        print("✅ Git Push 完成！")
        
    except Exception as e:
        print(f"❌ 更新 GitHub Pages 失敗: {e}")

def main():
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"🚀 開始執行 ETF 追蹤 ({today_str})")
    
    # 0. 抓取全市場今日收盤價 (估算建倉成本)
    market_prices = fetch_all_prices()

    # 1. 抓取今日 ETF 持股資料
    daily_data = {}
    for etf_id in ETF_TICKERS:
        holdings = fetch_etf_holdings_fallback(etf_id)
        if holdings:
            daily_data[etf_id] = holdings
            
    if not daily_data:
        print("❌ 沒有抓取到任何資料，結束程式。")
        return
        
    output_path = os.path.join(DATA_DIR, f"{today_str}_holdings.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(daily_data, f, ensure_ascii=False, indent=2)
    print(f"📁 當日資料已儲存至: {output_path}")

    # 2. 比對昨日資料
    prev_result = find_previous_data(today_str)
    if not prev_result:
        print("ℹ️ 找不到前一日資料，無法進行比對。")
        return
        
    prev_data, prev_date = prev_result
    print(f"🔍 開始與 {prev_date} 進行比對...")
    
    report_lines = [f"📊 **主動型 ETF 籌碼異動日報 ({today_str})** 📊\n"]
    has_changes = False
    
    for etf_id in ETF_TICKERS:
        if etf_id in daily_data and etf_id in prev_data:
            diff = diff_holdings(prev_data, daily_data, etf_id, market_prices)
            
            if diff["added"] or diff["removed"] or diff["changed"]:
                has_changes = True
                report_lines.append(f"🔥 **【{etf_id}】 異動快訊**")
                
                for item in diff["added"]:
                    cost_str = f" 💰 估算均價: ${item['cost_estimate']}" if item.get('cost_estimate') else ""
                    val_str = f" (~{item.get('diff_value', 0)/100000000:.2f}億)" if item.get('diff_value') else ""
                    report_lines.append(f"  🚨 **[新建倉]** {item['name']} ({item['shares']/1000:,.0f} 張){val_str}{cost_str}")
                for item in diff["removed"]:
                    val_str = f" (~{abs(item.get('diff_value', 0))/100000000:.2f}億)" if item.get('diff_value') else ""
                    report_lines.append(f"  💸 **[清倉剔除]** {item['name']} ({item['shares']/1000:,.0f} 張){val_str}")
                for item in diff["changed"]:
                    sign = "+" if item['diff'] > 0 else ""
                    cost_str = f" 💰 估算均價: ${item['cost_estimate']}" if item['diff'] > 0 and item.get('cost_estimate') else ""
                    val_str = f" (~{abs(item.get('diff_value', 0))/100000000:.2f}億)" if item.get('diff_value') else ""
                    report_lines.append(f"  🔄 **[加減碼]** {item['name']} {sign}{item['diff']/1000:,.0f} 張{val_str} (現有: {item['new_shares']/1000:,.0f} 張){cost_str}")
                report_lines.append("")
                
    report_text = "\n".join(report_lines)
    print("\n" + report_text)

    # 3. 自動更新 GitHub Pages
    if has_changes:
        diff_dict = {}
        for etf_id in ETF_TICKERS:
            if etf_id in daily_data and etf_id in prev_data:
                diff_dict[etf_id] = diff_holdings(prev_data, daily_data, etf_id, market_prices)
        update_github_pages(diff_dict, today_str, prev_date, daily_data)

if __name__ == "__main__":
    main()

# ETF Active Tracker (主動型 ETF 籌碼分析雷達)

這是一個全自動化的 Python + JavaScript (Puppeteer) 專案，專門用來追蹤台灣主動型 ETF (例如 `00981A 統一台股增長`、`00992A 群益科技創新`) 的每日成分股異動。

網頁展示版：[https://louisfghbvc.github.io/etf-analysis/](https://louisfghbvc.github.io/etf-analysis/)

## 功能特色
1. **全自動無頭爬蟲**：繞過投信官網防護，自動從理財寶等公開資訊源爬取「完整 50 檔成分股」。
2. **精準 Diff 引擎**：比對 T 日與 T-1 日的持股異動，抓出「新建倉」、「清倉」與「大加碼」的飆股。
3. **建倉成本估算**：串接台灣證券交易所 (TWSE) 與櫃買中心 (TPEx) OpenAPI，自動算出投信買進該股的「估算成本」與「動用資金(億)」。
4. **自動化發布管線**：
   - 每日 18:00 自動推播戰報至 Discord。
   - 自動運算 `CROSS_DATA` (交叉持股) 與 `HISTORY_DATA`。
   - 自動將最新的 JSON 寫入 `index.html`，並 Push 至 GitHub Pages。

## 資料安全與隱私
* 本專案前身借鏡自 Dcard 網友的 UI (Thanks to `zhaoyuanliu`)。
* **已移除所有的第三方 Firebase API Keys 與追蹤碼**，網頁現為 100% 靜態純淨版，沒有外部資料庫連結，保證資料安全。
* 本 Repository **未包含**個人的 Discord Webhook Token 或 OpenClaw 憑證，請放心 Fork。

## 如何執行
本專案依賴 Node.js (Puppeteer) 與 Python 3。
```bash
# 1. 安裝環境
npm install puppeteer-core
sudo apt-get install chromium

# 2. 執行更新腳本
python3 scripts/etf_tracker/update_etf.py
```

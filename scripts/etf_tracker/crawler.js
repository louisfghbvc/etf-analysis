const puppeteer = require('puppeteer-core');
const fs = require('fs');

const etfId = process.argv[2];
if (!etfId) {
    console.error("Please provide ETF ID");
    process.exit(1);
}

(async () => {
    try {
        const browser = await puppeteer.launch({ 
            executablePath: '/usr/bin/chromium',
            headless: "new",
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        const page = await browser.newPage();
        
        await page.goto(`https://www.cmoney.tw/etf/tw/${etfId.toLowerCase()}/fundholding`, { waitUntil: 'networkidle0', timeout: 30000 });
        
        // CMoney uses table.cm-table__table for the holdings list
        await page.waitForSelector('table.cm-table__table tr', { timeout: 10000 }).catch(e => {});
        
        const data = await page.evaluate(() => {
            let result = {};
            const rows = document.querySelectorAll('table.cm-table__table tr');
            for (let r of rows) {
                const cells = r.querySelectorAll('td, th');
                // Format: 代號 | 名稱 | 權重 | 持有數 | 單位
                if (cells.length >= 5) {
                    const ticker = cells[0].innerText.trim();
                    const name = cells[1].innerText.trim();
                    const weightStr = cells[2].innerText.replace('%', '').trim();
                    const sharesStr = cells[3].innerText.replace(/,/g, '').trim();
                    
                    // Skip Cash / Margin / Headers
                    if (ticker === '代號' || ticker.includes('NTD')) continue;
                    
                    const weight = parseFloat(weightStr) || 0;
                    const shares = parseFloat(sharesStr) || 0;
                    
                    result[ticker] = {
                        name: name,
                        weight: weight,
                        shares: shares
                    };
                }
            }
            return result;
        });
        
        console.log(JSON.stringify(data));
        await browser.close();
    } catch(e) {
        console.error("Error:", e);
        process.exit(1);
    }
})();

const puppeteer = require('puppeteer-core');
const fs = require('fs');

const etfId = process.argv[2];
if (!etfId) {
    console.error("Please provide ETF ID");
    process.exit(1);
}

(async () => {
    let browser;
    try {
        browser = await puppeteer.launch({ 
            executablePath: '/usr/bin/chromium',
            headless: "new",
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });
        const page = await browser.newPage();
        
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        
        await page.goto(`https://www.cmoney.tw/etf/tw/${etfId.toLowerCase()}/fundholding`, { waitUntil: 'domcontentloaded', timeout: 10000 });
        
        // Use a simpler approach: wait for selector or timeout, then evaluate
        await page.waitForSelector('table.cm-table__table tr', { timeout: 5000 }).catch(e => {});
        
        // short sleep
        await new Promise(r => setTimeout(r, 1000));
        
        const data = await page.evaluate(() => {
            let result = {};
            const rows = document.querySelectorAll('table.cm-table__table tr');
            for (let r of rows) {
                const cells = r.querySelectorAll('td, th');
                if (cells.length >= 5) {
                    const ticker = cells[0].innerText.trim();
                    const name = cells[1].innerText.trim();
                    const weightStr = cells[2].innerText.replace('%', '').trim();
                    const sharesStr = cells[3].innerText.replace(/,/g, '').trim();
                    
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
        process.exit(0);
    } catch(e) {
        console.error("Error:", e);
        if (browser) {
            try { await browser.close(); } catch(e){}
        }
        process.exit(1);
    }
})();

// 独立临时浏览器；不发送订单，不调用AI，不更改真实账户。
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'chrome'});try{const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(30000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.goto('http://localhost:3000/invest?view=functions&tool=fund&section=etf-universe',{waitUntil:'domcontentloaded'});await p.getByRole('heading',{name:'全ETF追踪',exact:true}).waitFor();const live=await(await p.request.get('http://localhost:8000/etfs')).json();assert(live.total>0);await p.getByText(String(live.total),{exact:true}).first().waitFor();
await p.getByRole('button',{name:'下一页',exact:true}).click();await p.getByText(/第2\//).waitFor();await p.getByRole('button',{name:'上一页',exact:true}).click();
await p.getByLabel('查询全ETF').fill('511880');await p.getByRole('button',{name:/银华日利/}).click();await p.getByRole('img',{name:/511880真实日K线/}).waitFor({timeout:60000});console.log('PASS all 1720, pagination, money ETF, shared real Kline');
await p.getByRole('link',{name:'打开基金深研与比较',exact:true}).click();await p.getByLabel('深研基金代码',{exact:true}).waitFor();assert.equal(await p.getByLabel('深研基金代码',{exact:true}).inputValue(),'511880');
await p.goto('http://localhost:3000/invest?view=functions&tool=fund&section=etf-universe',{waitUntil:'domcontentloaded'});await p.getByLabel('ETF资产类别').selectOption('货币');await p.locator('table:visible tbody tr').first().waitFor();assert(await p.locator('table:visible tbody tr').count()>0);
await p.getByLabel('ETF资产类别').selectOption('全部');await p.getByLabel('查询全ETF').fill('158000');await p.getByRole('button',{name:/158000/}).waitFor();console.log('PASS category filter, new 158 code, research context');
await p.goto('http://localhost:3000/invest?view=strategies',{waitUntil:'domcontentloaded'});const links=p.getByRole('link',{name:/^打开/});await p.getByRole('link',{name:'打开SHIBOR红利成长轮动',exact:true}).waitFor();assert.equal(await links.count(),8);await p.getByRole('link',{name:'打开SHIBOR红利成长轮动',exact:true}).click();await p.getByRole('heading',{name:'SHIBOR轮动 · 前向模拟账户',exact:true}).waitFor();await p.getByText(/实际启动/).first().waitFor();
for(const width of [390,820,1440]){await p.setViewportSize({width,height:1000});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'strategy overflow '+width);}
console.log('PASS eighth page, account data, three widths');
await p.goto('http://localhost:3000/invest?view=functions&tool=fund&section=etf-universe',{waitUntil:'domcontentloaded'});await p.getByLabel('查询全ETF').waitFor();
for(const width of [390,820,1440]){await p.setViewportSize({width,height:1000});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'ETF overflow '+width);}
assert.deepEqual(errors,[]);console.log('PASS ETF three widths and no JavaScript errors');
}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});

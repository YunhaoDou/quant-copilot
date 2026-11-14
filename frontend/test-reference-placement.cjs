const {chromium}=require('./scripts/test-browser.cjs');const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'chrome'});try{const p=await b.newPage();p.setDefaultTimeout(20000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
const quotes=p.getByRole('heading',{name:'真实行情参考',exact:true}),legacy=p.getByRole('heading',{name:'遗留美股策略模拟（只读）',exact:true});
const strategies=(await(await p.request.get('http://localhost:8000/strategy-center/overview')).json()).strategies;
for(const view of ['decision','market','research','trade','data','help']){await p.goto('http://localhost:3000/invest?view='+view);await p.getByRole('heading',{name:'A股投资决策中心',exact:true}).waitFor();await p.waitForTimeout(400);assert.equal(await quotes.count(),view==='decision'?1:0,'quote placement '+view);}
await p.goto('http://localhost:3000/invest?view=trade&tab=strategies');await legacy.waitFor();
for(const s of strategies){await p.getByRole('link',{name:'打开'+s.name,exact:true}).click();await p.getByRole('heading',{name:s.name,exact:true}).waitFor();assert.equal(await legacy.count(),0,'legacy hidden '+s.id);assert.equal(await quotes.count(),0);await p.goto('http://localhost:3000/invest?view=trade&tab=strategies');await legacy.waitFor();}
assert.equal(errors.length,0,JSON.stringify(errors));console.log('PASS quotes only on decision; legacy only on strategy home, absent on all eight detail pages');}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

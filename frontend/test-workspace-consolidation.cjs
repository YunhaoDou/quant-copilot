// 使用独立临时浏览器验证「6 个工作流页面」的整合；不调用AI、通知、下单或账户启停接口。
// 页面映射：decision(驾驶舱/复盘) · market(雷达/周期) · research(红利/观察池/研究)
//           trade(策略/模拟工具/回测/手动模拟/档案) · data(行情/选股/基金) · help(指南/设置/合规)
const {chromium}=require('./scripts/test-browser.cjs');
const assert=require('node:assert/strict');
const current=(p)=>new URL(p.url()).searchParams;
(async()=>{const b=await chromium.launch({channel:'chrome'});try{
const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(25000);const errors=[];p.on('pageerror',e=>errors.push(e.message));
const go=(url)=>p.goto('http://localhost:3000/invest?'+url,{waitUntil:'domcontentloaded'});

// 1) 交易与模拟 → 历史回测（原功能中心里的回测）
await go('view=trade');await p.getByRole('button',{name:/^历史回测/}).click();
const source=p.getByLabel('回测数据读取方式');await source.waitFor();assert.equal(await source.inputValue(),'direct');
await p.getByRole('button',{name:'运行对比',exact:true}).click();await p.getByText(/直接读取真实前复权日线，不写入归档/).waitFor({timeout:60000});assert.equal(await p.locator('table.mt-8:visible tbody tr').count(),5);
await source.selectOption('archive');assert.equal(await p.locator('table.mt-8:visible tbody tr').count(),0);console.log('PASS single historical UI, real direct data, five strategies, archive mode');

// 2) 旧功能中心的工具深链仍可用，并自动规范化到新页面
await go('view=functions&tool=fund&section=fund-research');await p.getByRole('button',{name:'基金深研与比较',exact:true}).click();await p.getByText('深研基金代码',{exact:true}).waitFor();await p.reload();await p.getByText('深研基金代码',{exact:true}).waitFor();
assert.equal(current(p).get('view'),'data');assert.equal(current(p).get('tab'),'fund');console.log('PASS legacy tool deep-link -> data/fund, section survives reload');

await go('view=trade');await p.getByRole('button',{name:'分析档案',exact:true}).click();await p.getByRole('button',{name:'查询档案',exact:true}).waitFor();
await go('view=help');await p.getByRole('button',{name:'系统设置',exact:true}).click();await p.getByRole('button',{name:'模型与通知',exact:true}).click();await p.getByRole('heading',{name:'模型配置 · 密钥仅保存在本机后端',exact:true}).waitFor();console.log('PASS archive + settings under their workflow pages');

// 3) 研究：三个子页签共用同一个公司上下文
await go('view=research&tab=research');await p.getByPlaceholder('如 600519 或 000001').fill('600320');await p.getByRole('button',{name:'打开公司研究',exact:true}).click();await p.getByRole('heading',{name:'振华重工 · 600320',exact:true}).waitFor();
await p.getByRole('button',{name:'技术诊断与追问',exact:true}).click();assert.equal(await p.getByLabel('诊断证券代码',{exact:true}).inputValue(),'600320');
await p.getByRole('button',{name:'AI结构化笔记',exact:true}).click();assert(await p.locator('input').evaluateAll(es=>es.some(e=>e.value==='600320')));
await p.getByRole('button',{name:'公司论证',exact:true}).click();await p.getByRole('heading',{name:'振华重工 · 600320',exact:true}).waitFor();console.log('PASS one company context across thesis, diagnosis, AI note');

// 4) 交易与模拟 → 模拟工具（组合推演 + 浏览器后退）
await go('view=trade&tab=tools');await p.getByRole('button',{name:'组合概率推演',exact:true}).click();await p.getByRole('heading',{name:'蒙特卡洛 · 假设情景',exact:true}).waitFor();await p.goBack();await p.getByRole('heading',{name:'仓位冲击模拟器',exact:true}).waitFor();console.log('PASS unique simulation tools and browser back');

// 5) 市场：股债趋势仍是市场雷达的内部页签
await go('view=market&section=allocation');await p.getByRole('button',{name:'更新真实日线',exact:true}).waitFor();console.log('PASS stock-bond trend inside market workflow');

// 6) 情绪周期 → 策略账户跳转
await go('view=market&tab=cycle&cycleTab=simulation');await p.getByRole('heading',{name:'情绪龙头回补',exact:true}).waitFor();assert.equal(current(p).get('view'),'trade');assert.equal(current(p).get('tab'),'strategies');console.log('PASS old cycle simulation link reaches single strategy account');

// 7) 旧视图别名全部规范化到 6 个页面之一
for(const [legacy,view] of [['dashboard','decision'],['watchlist','research'],['strategies','trade'],['guide','help'],['functions','data']]){await go('view='+legacy);await p.waitForTimeout(300);assert.equal(current(p).get('view'),view,`legacy ${legacy}`);}
await go('view=functions&tool=sim');await p.getByLabel('回测数据读取方式').waitFor();console.log('PASS legacy view/tool aliases normalize to the 6 workflow pages');

for(const width of [390,820,1440]){await p.setViewportSize({width,height:1000});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow ${width}`);}
assert.deepEqual(errors,[]);console.log('PASS compatibility links, three widths, no JavaScript exceptions');
}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});

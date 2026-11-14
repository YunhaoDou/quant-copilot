// 自动验收默认只读：页面级测试夹具可覆盖，但不会放行真实AI、通知或账户操作。
const base=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const guarded=new WeakSet();
async function protect(context){
 if(guarded.has(context))return;guarded.add(context);
 await context.route('**/*',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())?route.continue():route.abort('blockedbyclient'));
 for(const name of ['post','put','patch','delete'])context.request[name]=()=>Promise.reject(new Error('自动验收禁止真实写入请求'));
 const original=context.request.fetch.bind(context.request);
 context.request.fetch=(url,options={})=>{
  const method=(options.method||(typeof url.method==='function'?url.method():'GET')).toUpperCase();
  if(!['GET','HEAD','OPTIONS'].includes(method))return Promise.reject(new Error('自动验收禁止真实写入请求'));
  return original(url,options);
 };
}
module.exports={chromium:{launch:async options=>{
 const browser=await base.chromium.launch(options);
 const newContext=browser.newContext.bind(browser),newPage=browser.newPage.bind(browser);
 browser.newContext=async(...args)=>{const context=await newContext(...args);await protect(context);return context;};
 browser.newPage=async(...args)=>{const page=await newPage(...args);await protect(page.context());return page;};
 return browser;
}}};

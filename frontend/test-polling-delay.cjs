// 验证故障退避边界，直接加载同一TypeScript纯函数，不访问网络。
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync(require('node:path').join(__dirname,'lib/polling-delay.ts'),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const result={};vm.runInNewContext(js,{exports:result});const delay=result.pollingDelay;
assert.equal(delay(30000,0,true),30000);assert.equal(delay(30000,1,true),30000);assert.equal(delay(30000,2,true),60000);assert.equal(delay(30000,3,true),120000);assert.equal(delay(30000,100,true),120000);
assert.equal(delay(300000,10,true),300000);assert.equal(delay(0,10,true),0);assert.equal(delay(-1,10,true),0);assert.equal(delay(NaN,10,true),0);assert.equal(delay(30000,10,false),30000);
console.log('PASS bounded retries, original intervals, replay zero polling and reset');

"use client";
import {useReadResource} from "@/lib/read-resource";
import {marketApiUrl} from "@/lib/live-market";
import {Card} from "./ui";
type Gate={total:number;background_limit:number;active:number;background_active:number;waiting:number;requests:number;wait_seconds:number};
type Data={cache:Record<string,number>;market_cache?:{daily_bytes:number;daily_budget:number;daily_entries:number;quote_entries:number};market:Record<string,Gate>;sqlite_wal_bytes:number;note:string;independent_iopv?:{status:string;enabled:boolean;scope:string;documentation_url:string}};
const mb=(n:number|undefined)=>n==null?"未知":(n/1024/1024).toFixed(1)+" MiB";
export default function RuntimeStatusPanel(){
 const r=useReadResource<Data>(`${marketApiUrl()}/health/resources`,5000,{backoff:true});
 return <Card><h2 className="text-xl font-semibold">运行与性能</h2><p className="mt-2 text-sm text-slate-500">只读资源状态，5秒刷新；隐藏页面暂停。数值不是收益或行情质量评分。</p>{r.error&&<p role="alert" className="mt-3 text-sm text-amber-800">暂不可读取：{r.error}</p>}
 <div className="mt-4 grid gap-3 sm:grid-cols-3">{[['document','文档缓存'],['model','查询快照'],['body','响应缓存']].map(([k,label])=><div key={k} className="rounded-xl bg-slate-50 p-4"><p className="text-sm">{label}</p><p className="mt-2 font-semibold">{mb(r.data?.cache[k+'_bytes'])} / {mb(r.data?.cache[k+'_budget'])}</p></div>)}</div>
 <p className="mt-3 text-sm">日线缓存：{mb(r.data?.market_cache?.daily_bytes)} / {mb(r.data?.market_cache?.daily_budget)} · {r.data?.market_cache?.daily_entries??"未知"}组；报价缓存 {r.data?.market_cache?.quote_entries??"未知"}项</p><div className="mt-4 space-y-3">{Object.entries(r.data?.market||{}).map(([name,g])=><p className="text-sm" key={name}>{name==='quotes'?'公共报价':'历史日线'}：使用 {g.active}/{g.total}，后台 {g.background_active}/{g.background_limit}，排队 {g.waiting}，累计 {g.requests} 次，累计等待 {g.wait_seconds.toFixed(2)} 秒</p>)}</div><p className="mt-4 text-xs text-slate-500">SQLite WAL：{mb(r.data?.sqlite_wal_bytes)}。只观察大小，不在页面触发清理或删除。</p><p className="mt-3 text-sm">独立IOPV备用源：{r.data?.independent_iopv?.status||"未知"}。{r.data?.independent_iopv?.scope}；东方财富同源备用节点不等于独立核验。</p><p className="mt-2 text-xs text-slate-500">{r.data?.note}</p></Card>;
}

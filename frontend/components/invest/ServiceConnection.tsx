"use client";
import {useReadResource} from "@/lib/read-resource";
import {marketApiUrl} from "@/lib/live-market";

/** 连接状态单独显示，不把已有页面或历史数据清空。 */
export default function ServiceConnection(){
 const result=useReadResource<{status:string}>(`${marketApiUrl()}/health/live`,data=>data?15000:2000);
 if(!result.error&&result.data?.status==="alive")return null;
 return <div role="status" aria-live="polite" className="my-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{result.error?"后台暂不可用，正在自动重连。现有页面数据不代表已刷新，请等待连接恢复。":"正在连接后台服务…"}</div>;
}

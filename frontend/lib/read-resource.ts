"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {pollingDelay} from "./polling-delay";

type Entry={data:unknown;etag:string|null;updated:number};
const cache=new Map<string,Entry>();
const flights=new Map<string,{promise:Promise<unknown>;controller:AbortController;users:number}>();
class ReadError extends Error{constructor(message:string,public status:number){super(message);}}

function acquire<T>(url:string,force=false){
 const old=cache.get(url);
 if(!force&&old&&Date.now()-old.updated<500)return {promise:Promise.resolve(old.data as T),release:()=>{}};
 let flight=flights.get(url);
 if(!flight||flight.controller.signal.aborted){
  const controller=new AbortController();
  const entry={controller,users:0,promise:null as unknown as Promise<unknown>};
  entry.promise=fetch(url,{signal:controller.signal,cache:"no-store",headers:old?.etag?{"If-None-Match":old.etag}:{}}).then(async r=>{
   if(r.status===304&&old){old.updated=Date.now();return old.data;}
   const data=await r.json();if(!r.ok)throw new ReadError(typeof data.detail==="string"?data.detail:"读取失败",r.status);
   cache.delete(url);cache.set(url,{data,etag:r.headers.get("etag"),updated:Date.now()});
   while(cache.size>128)cache.delete(cache.keys().next().value!);
   return data;
  }).finally(()=>{if(flights.get(url)===entry)flights.delete(url);});
  flight=entry;flights.set(url,entry);
 }
 flight.users++;let released=false;
 return {promise:flight.promise as Promise<T>,release:()=>{if(released)return;released=true;if(--flight!.users===0)flight!.controller.abort();}};
}

/** 一次请求完成后再计时；隐藏标签页暂停；同URL合并；旧响应不会覆盖新查询。 */
export function useReadResource<T>(url:string|null,interval:number|((data:T|null)=>number)=15000,options:{backoff?:boolean;clearOnChange?:boolean;clearOnError?:boolean;revalidateOnVisible?:boolean}={}){
 const [data,setData]=useState<T|null>(null),[error,setError]=useState(""),[errorStatus,setErrorStatus]=useState<number|null>(null),[loading,setLoading]=useState(false),[revision,setRevision]=useState(0);
 const intervalRef=useRef(interval);intervalRef.current=interval;
 const optionsRef=useRef(options);optionsRef.current=options;
 const refresh=useCallback(()=>setRevision(v=>v+1),[]);
 useEffect(()=>{
  if(!url)return;
  if(optionsRef.current.clearOnChange){setData(null);setError("");setErrorStatus(null);}
  let failures=0,hasStarted=false;
  let active=true,busy=false,timer:ReturnType<typeof setTimeout>|undefined,release:(()=>void)|undefined;
  async function run(){
   if(!active||busy||document.hidden)return;
   hasStarted=true;busy=true;setLoading(true);let result:T|null=null;
   try{const task=acquire<T>(url!,revision>0);release=task.release;result=await task.promise;failures=0;if(active){setData(result);setError("");setErrorStatus(null);}}
   catch(e){if(active&&!(e instanceof DOMException&&e.name==="AbortError")){failures++;setError(String(e));setErrorStatus(e instanceof ReadError?e.status:null);if(optionsRef.current.clearOnError)setData(null);}}
   finally{release?.();release=undefined;busy=false;if(active){setLoading(false);const fn=intervalRef.current,base=typeof fn==="function"?fn(result):fn,delay=pollingDelay(base,failures,!!optionsRef.current.backoff);if(delay>0)timer=setTimeout(run,delay);}}
  }
  function visible(){if(timer)clearTimeout(timer);if(!document.hidden&&(!hasStarted||optionsRef.current.revalidateOnVisible!==false))run();}
  document.addEventListener("visibilitychange",visible);run();
  return()=>{active=false;if(timer)clearTimeout(timer);release?.();document.removeEventListener("visibilitychange",visible);};
 },[url,revision]);
 return {data,error,errorStatus,loading,refresh};
}

export function useDebouncedValue<T>(value:T,ms=250){const [result,setResult]=useState(value);useEffect(()=>{const timer=setTimeout(()=>setResult(value),ms);return()=>clearTimeout(timer);},[value,ms]);return result;}

/** 兼容现有账户动作接口：可见时串行轮询，卸载时取消未完成读取。 */
export function useVisiblePoll(load:(signal:AbortSignal)=>Promise<void>,delay:number){
 const callback=useRef(load);callback.current=load;
 useEffect(()=>{
  const controller=new AbortController();let active=true,busy=false,timer:ReturnType<typeof setTimeout>|undefined;
  async function run(){if(!active||busy||document.hidden)return;busy=true;
   try{await callback.current(controller.signal);}finally{busy=false;if(active)timer=setTimeout(run,delay);}
  }
  function visible(){if(timer)clearTimeout(timer);if(!document.hidden)run();}
  document.addEventListener("visibilitychange",visible);run();
  return()=>{active=false;controller.abort();if(timer)clearTimeout(timer);document.removeEventListener("visibilitychange",visible);};
 },[delay]);
}

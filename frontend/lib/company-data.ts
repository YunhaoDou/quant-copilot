"use client";
import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { PersonalInvestmentState } from "./personal-investment";
import { companyCode, CompanyInfo } from "./company-store";
import { marketApiUrl } from "./live-market";

const cache=new Map<string,{time:number;promise:Promise<CompanyInfo>}>();
export function fetchCompanyInfo(value:string):Promise<CompanyInfo>{
 const code=companyCode(value);if(!code)return Promise.reject(new Error("请输入六位A股股票代码，指数和基金请到对应工具查看。"));
 const old=cache.get(code);if(old&&Date.now()-old.time<300000)return old.promise;
 const promise=fetch(`${marketApiUrl()}/companies/${code}`,{cache:"no-store"}).then(async r=>{const p=await r.json();if(!r.ok)throw new Error(typeof p.detail==="string"?p.detail:"公司识别失败");if(p.code!==code||!p.name||!p.quote||p.quote.price<=0)throw new Error("未取得完整公司身份信息");return p as CompanyInfo;}).catch(e=>{cache.delete(code);throw e;});
 if(cache.size>200)cache.delete(cache.keys().next().value!);cache.set(code,{time:Date.now(),promise});return promise;
}
export function useCompanyProfiles(codes:string[],setState:Dispatch<SetStateAction<PersonalInvestmentState>>){
 const key=[...new Set(codes)].sort().join(","),[errors,setErrors]=useState<Record<string,string>>({});
 useEffect(()=>{let active=true;async function load(){const queue=key.split(",").filter(Boolean);async function worker(){while(active&&queue.length){const code=queue.shift()!;try{const info=await fetchCompanyInfo(code);if(active){setState(s=>{const c=s.companies?.[code];if(!c||c.info?.fetchedAt===info.fetchedAt)return s;return {...s,companies:{...s.companies,[code]:{...c,name:info.name,info}}};});setErrors(e=>{const next={...e};delete next[code];return next;});}}catch(e){if(active)setErrors(old=>({...old,[code]:String(e)}));}}}await Promise.all([worker(),worker()]);}load();const timer=setInterval(load,300000);return()=>{active=false;clearInterval(timer);};},[key,setState]);return errors;
}

import type { PersonalInvestmentState, ResearchNote, WatchItem } from "./personal-investment";

export type CompanyInfo={code:string;name:string;symbol:string;industry:string|null;industrySource?:string|null;quote:{price:number;pe:number|null;pb:number|null;pct:number;quote_time:string};quoteSource:string;fetchedAt:string;dividend:{cashPerShare:number|null;dividendYield:number|null;asOf:string;source:string;note:string;verified:boolean;consecutiveYears?:number};warnings:string[];quality:null};
export type CompanyResearch={opened:boolean;businessModel:string;financialTrend:string;valuationThesis:string;catalysts:string;bearCase:string;invalidation:string;targetLow:number|null;targetHigh:number|null;updatedAt:string;legacyRangeConflict?:boolean};
export type CompanyProfile={code:string;name:string;info?:CompanyInfo;inWatchlist:boolean;trackingStatus:"观察"|"排除";origin:string;riskTags:string;research:CompanyResearch;createdAt:string};
export type CompanyArchive={watchlist:WatchItem[];research:ResearchNote[];invalidCodes:string[];migratedAt:string};

export function companyCode(input:string):string|null{
 const s=input.trim().toUpperCase(),m=s.match(/^(?:(SH|SZ|BJ))?(\d{6})(?:\.(SS|SH|SZ|BJ))?$/);
 if(!m)return null;const code=m[2],expected=code.startsWith("6")?"SH":/^[03]/.test(code)?"SZ":/^(4|8|92)/.test(code)?"BJ":null;
 if(!expected||expected==="SH"&&!/^(600|601|603|605|688|689)/.test(code)||expected==="SZ"&&!/^(000|001|002|003|300|301)/.test(code))return null;
 const exchange=m[1]||(m[3]==="SS"?"SH":m[3]);return exchange&&exchange!==expected?null:code;
}
export function emptyCompany(code:string,name=code):CompanyProfile{return {code,name,inWatchlist:false,trackingStatus:"观察",origin:"代码识别",riskTags:"",createdAt:new Date().toISOString(),research:{opened:false,businessModel:"",financialTrend:"",valuationThesis:"",catalysts:"",bearCase:"",invalidation:"",targetLow:null,targetHigh:null,updatedAt:""}};}
function mergeText(a:string,b:string){if(!b?.trim()||a===b)return a;return a?`${a}\n\n【合并的历史记录】\n${b}`:b;}

/** 唯一活动公司表；旧数组原样归档一次，后续不再作为写入或显示来源。 */
export function migrateCompanies(state:PersonalInvestmentState):PersonalInvestmentState{
 if(state.companySchemaVersion===1)return state;
 const companies=Object.fromEntries(Object.entries(state.companies||{}).map(([k,v])=>[k,{...v,research:{...v.research}}])),invalidCodes:string[]=[];
 for(const item of state.watchlist||[]){const code=companyCode(String(item.code));if(!code){invalidCodes.push(String(item.code));continue;}const c=companies[code]||emptyCompany(code,item.name);c.inWatchlist=true;c.name=item.name||c.name;if(item.status==="排除")c.trackingStatus="排除";c.riskTags=mergeText(c.riskTags,item.riskTags);c.origin="原观察池迁入";
  if(item.targetLow>0&&item.targetHigh>=item.targetLow&&!c.research.legacyRangeConflict){if(c.research.targetLow!=null&&(c.research.targetLow!==item.targetLow||c.research.targetHigh!==item.targetHigh)){c.research.targetLow=null;c.research.targetHigh=null;c.research.legacyRangeConflict=true;}else{c.research.targetLow=item.targetLow;c.research.targetHigh=item.targetHigh;}}companies[code]=c;}
 for(const item of state.research||[]){const code=companyCode(String(item.code));if(!code){invalidCodes.push(String(item.code));continue;}const c=companies[code]||emptyCompany(code,item.name);c.name=item.name||c.name;c.research.opened=true;
  for(const key of ["businessModel","financialTrend","valuationThesis","catalysts","bearCase","invalidation"] as const)c.research[key]=mergeText(c.research[key],item[key]);c.research.updatedAt=item.updatedAt||c.research.updatedAt;companies[code]=c;}
 const archive=state.companyLegacyArchive||((state.watchlist?.length||state.research?.length)?{watchlist:state.watchlist,research:state.research,invalidCodes,migratedAt:new Date().toISOString()}:undefined);
 return {...state,companies,companySchemaVersion:1,companyLegacyArchive:archive,watchlist:[],research:[]};
}
export function upsertCompany(state:PersonalInvestmentState,info:CompanyInfo,mode:"watch"|"research"|"view",origin="代码识别"){
 const current=migrateCompanies(state),code=companyCode(info.code);if(!code)throw new Error("证券代码无效");
 const old=current.companies?.[code]||emptyCompany(code,info.name);
 return {...current,companies:{...current.companies,[code]:{...old,name:info.name,info,inWatchlist:mode==="watch"?true:old.inWatchlist,origin:old.inWatchlist?old.origin:origin,research:{...old.research,opened:mode==="research"?true:old.research.opened}}}};
}
export function openCompanyResearch(state:PersonalInvestmentState,code:string){const c=state.companies?.[code];if(!c)return state;return {...state,companies:{...state.companies,[code]:{...c,research:{...c.research,opened:true}}}};}
export function patchCompanyResearch(state:PersonalInvestmentState,code:string,changes:Partial<CompanyResearch>){const c=state.companies?.[code];if(!c)return state;return {...state,companies:{...state.companies,[code]:{...c,research:{...c.research,...changes,updatedAt:new Date().toISOString()}}}};}
export function researchZone(price:number|null|undefined,c:CompanyProfile){const {targetLow:low,targetHigh:high}=c.research;if(price==null||price<=0)return "行情未知";if(low==null||high==null)return "未设研究区间";return price<low?"低于研究区间":price<=high?"进入研究区间":"高于研究区间";}

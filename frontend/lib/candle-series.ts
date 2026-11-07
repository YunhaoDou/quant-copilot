export type CandleBar={date:string;open:number;high:number;low:number;close:number;volume:number};
export function candleSeries(bars:CandleBar[]){return bars.map((b,i)=>({...b,ma20:i>=19?bars.slice(i-19,i+1).reduce((n,r)=>n+r.close,0)/20:null,ma60:i>=59?bars.slice(i-59,i+1).reduce((n,r)=>n+r.close,0)/60:null,ma200:i>=199?bars.slice(i-199,i+1).reduce((n,r)=>n+r.close,0)/200:null}));}

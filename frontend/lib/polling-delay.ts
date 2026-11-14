/** 失败时有界退避；成功后恢复原间隔，离线/回放的0间隔不变。 */
export function pollingDelay(base:number,failures:number,backoff:boolean){
 if(!(base>0))return 0;
 if(!backoff||failures<=1)return base;
 return Math.max(base,Math.min(120000,base*2**Math.min(failures-1,6)));
}

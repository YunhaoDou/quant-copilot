"""本机模拟服务客户端；只允许回环地址和已列出的模拟控制。"""
import json
from urllib.parse import urlparse, urlencode
from urllib.request import build_opener, ProxyHandler, Request

STRATEGIES = {
    "quality-value":"质量价值", "dividend-cash":"红利现金流", "dividend-lowvol":"红利低波",
    "fundamental-trend":"基本面改善后趋势入场", "relative-trend":"相对强势趋势",
    "leader-rebound":"情绪龙头回补", "trend-leader-band":"主线趋势中军波段",
}

class LocalClient:
    def __init__(self, base_url="http://127.0.0.1:8000", timeout=8):
        parsed=urlparse(base_url)
        if parsed.scheme!="http" or parsed.hostname not in ("127.0.0.1","localhost") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("仅允许本机Quant Copilot模拟服务")
        self.base_url=base_url.rstrip("/");self.timeout=timeout
        self.opener=build_opener(ProxyHandler({}))

    def request(self,path,method="GET"):
        req=Request(self.base_url+path,method=method,headers={"Accept":"application/json"})
        with self.opener.open(req,timeout=self.timeout) as response:
            raw=response.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError("本机服务响应超出限制")
        return json.loads(raw)

    def snapshot(self):
        data=self.request("/strategy-center")
        if {s["id"] for s in data.get("strategies",[])} != set(STRATEGIES):
            raise ValueError("后端未提供完整七策略，请先启动当前Quant Copilot")
        legacy=self.request("/cycle/strategy-sim")
        for spec in data["strategies"]:
            if spec["id"]=="leader-rebound":spec["account"]=legacy.get("account")
        return data

    def command(self,strategy,action):
        if strategy not in STRATEGIES or action not in ("start","pause","exit"):
            raise ValueError("不支持的模拟控制")
        path=(f"/cycle/strategy-sim/{action}" if strategy=="leader-rebound" else
              f"/trend-forward/{action}" if strategy=="trend-leader-band" else
              f"/strategy-center/{strategy}/{action}")
        return self.request(path,"POST")

    def quotes(self,symbols):
        return self.request("/market/quotes?"+urlencode({"symbols":",".join(symbols)}))

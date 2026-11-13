"""共同观察期与范围切换审计，保留旧账户，不回填未知历史。"""
from datetime import datetime
import json
from app.cycle.events import database, encode
from app.cycle.engine import load_config
from app.cycle.live import TZ


def setup():
    # 已建立的实验只读，不因查看目录抢占模拟账户的写锁。
    with database() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='strategy_experiment'").fetchone():
            row=db.execute("SELECT payload FROM strategy_experiment WHERE id=1").fetchone()
            if row:return json.loads(row[0])
    cfg=load_config();now=datetime.now(TZ).isoformat()
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS strategy_experiment (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS strategy_scope_backup (name TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        row=db.execute("SELECT payload FROM strategy_experiment WHERE id=1").fetchone()
        if row:return json.loads(row[0])
        coverage=[]
        for table,key in (("research_strategy_accounts","strategy_id"),("strategy_sim","id"),("trend_forward_account","id")):
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if not exists:continue
            for name,payload in db.execute(f"SELECT {key},payload FROM {table}").fetchall():
                db.execute("INSERT OR IGNORE INTO strategy_scope_backup VALUES(?,?)",(table+":"+str(name),payload))
                account=json.loads(payload)
                account["inception_date"]=cfg["experiment_start_date"]
                account["universe_changed_at"]=now
                for trade in account.get("trades",[]):trade.setdefault("universe_scope","切换全A股之前的原范围")
                db.execute(f"UPDATE {table} SET payload=? WHERE {key}=?",(encode(account),name))
                coverage.append({"account":table+":"+str(name),"actual_created_at":account.get("created_at"),"pre_switch_trades":len(account.get("trades",[]))})
        result={"start_date":cfg["experiment_start_date"],"review_date":cfg["experiment_review_date"],"scope":"all-a",
            "changed_at":now,"coverage":coverage,
            "notes":["未满足策略条件时空仓；缺失数据标记为无法核验，不伪称已验证无信号。", "共同观察期从2026-11-11开始；切换之前缺少全A股前向采集，不能补造当时交易。", "原账户、已有成交及收益保留；切换前交易单独标注原范围，不冒充全A股实验成交。", "完整母池不等于全市场实时扫描已完成；逐轮展示实际处理数量与错误。"]}
        db.execute("INSERT INTO strategy_experiment VALUES(1,?)",(encode(result),))
        return result

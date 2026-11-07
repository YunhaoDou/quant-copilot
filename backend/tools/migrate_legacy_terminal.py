"""先备份并校验旧终端源文件，再迁移私有配置与历史；本脚本不删除源目录。"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import research_store as store


def migrate(source: Path, destination: Path):
    if not source.is_dir() or source.is_symlink():
        raise ValueError("源目录不存在或不是实体目录")
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    excluded = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "node_modules"}
    files = [p for p in source.rglob("*") if p.is_file() and not any(part in excluded for part in p.relative_to(source).parts)]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = destination / f"legacy-terminal-{stamp}.tar.gz"
    hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    external = Path.home() / ".fund_terminal"
    with tarfile.open(archive, "w:gz") as tar:
        for p in files:
            tar.add(p, arcname=str(p.relative_to(source)), recursive=False)
        for p in external.glob("*.json"):
            tar.add(p, arcname="fund-terminal-home/" + p.name, recursive=False)
    archive.chmod(0o600)
    with tarfile.open(archive) as tar:
        for name, digest in hashes.items():
            stream = tar.extractfile(name)
            if stream is None or hashlib.sha256(stream.read()).hexdigest() != digest:
                raise ValueError("备份校验失败，禁止移除源目录")
    config_path = source / "fund/config.json"
    original = json.loads(config_path.read_text()) if config_path.exists() else {}
    changes = {"providers": {}, **original.get("preferences", {})}
    for pid, p in original.get("providers", {}).items():
        if pid in store.DEFAULTS["providers"]:
            changes["providers"][pid] = {k:p[k] for k in ("api_key", "base_url") if p.get(k)}
    active = original.get("active_provider")
    home_settings = external / "settings.json"
    previous = json.loads(home_settings.read_text()) if home_settings.exists() else {}
    current = store.config()
    for pid in store.DEFAULTS["providers"]:
        key = previous.get("api_key_" + pid)
        if key and not store.secret_for(pid, current) and not changes["providers"].get(pid, {}).get("api_key"):
            changes["providers"].setdefault(pid, {})["api_key"] = key
        if previous.get("active_provider") == pid and previous.get("active_model") and not current["providers"][pid].get("model"):
            changes["providers"].setdefault(pid, {})["model"] = previous["active_model"]
    alerts = original.get("alerts") or {}
    if alerts:
        high, low = float(alerts.get("premium_upper", 1.5)), float(alerts.get("premium_lower", -1.5))
        changes["alerts"] = dict(warning_high=high, danger_high=max(3, high * 2), warning_low=low, danger_low=min(-3, low * 2))
    # 旧配置若没有可用密钥，继续使用主系统已配置的DeepSeek，而非无依据宣称旧模型已连通。
    if active and original.get("providers", {}).get(active, {}).get("api_key"):
        changes.update(active_provider=active, model=original.get("active_model", ""))
    proxy = original.get("proxy") or {}
    if isinstance(proxy, dict) and proxy.get("enabled") and proxy.get("url"):
        changes["proxy"] = proxy["url"]
    store.save_config(changes)
    imported = 0
    history_path = source / "fund/data/history.db"
    if history_path.exists():
        with sqlite3.connect(f"file:{history_path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM fund_history").fetchall()
        for r in rows:
            data = dict(r)
            payload = dict(kind="legacy", code=data.get("code", ""), name=data.get("name", ""),
                source="旧终端已保存档案，未重新核验真实行情", as_of=data.get("timestamp"),
                summary=data.get("ai_summary", ""), premium_rate=data.get("premium_rate"), warnings=["旧记录保留原值，不等同当前真实数据。"])
            store.save_report(payload, legacy_key="legacy-sqlite:" + str(data["id"]))
            imported += 1
    for origin, rows in (("config", original.get("search_history", [])), ("home", json.loads((external / "history.json").read_text()) if (external / "history.json").exists() else [])):
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            payload = dict(kind="legacy", code=str(row.get("code", "")), name=row.get("name", ""), source="旧终端搜索历史，未核验", summary=row.get("ai_summary", row.get("summary", "")), as_of=row.get("timestamp"))
            store.save_report(payload, legacy_key=f"legacy-json:{origin}:{index}")
            imported += 1
    manifest = {"source": str(source), "archive": str(archive), "verified_files": len(hashes), "source_hashes": hashes, "history_records_processed": imported, "config_migrated": True, "source_removed": False, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    manifest_path = destination / f"manifest-{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    manifest_path.chmod(0o600)
    return {k:v for k,v in manifest.items() if k != "source_hashes"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--backup-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data/legacy-terminal-backup")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.backup_dir), ensure_ascii=False))

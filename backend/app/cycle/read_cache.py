"""只读快照缓存与条件响应；不删证券、不改模拟账本。"""
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import RLock
from time import monotonic
import gzip
import json
import sqlite3
from fastapi import HTTPException, Request, Response

_lock=RLock()
_documents={}
_models={}
_bodies=OrderedDict()
_body_bytes=0
_document_locks={}
_model_locks={}
_document_epoch=0


def _key_lock(registry,key):
    # 全局锁只保护注册表和响应LRU；IO、JSON解析及模型构建使用独立锁。
    with _lock:return registry.setdefault(key,RLock())


def document(path,table,ttl=1.):
    """完整文档最多每秒核对一次；比较原文以识别同时间戳的实际修改。"""
    key=(str(Path(path).resolve()),table)
    with _key_lock(_document_locks,key):
        with _lock:
            old=_documents.get(key);epoch=_document_epoch
        now=monotonic()
        if old and now-old[0]<ttl:return old[1],old[2]
        raw=None
        if Path(path).exists():
            # sqlite连接上下文只提交/回滚，需显式关闭以及时释放读事务。
            db=sqlite3.connect(path,timeout=3)
            try:
                db.execute("PRAGMA query_only=ON")
                try:row=db.execute(f"SELECT payload FROM {table} WHERE id=1").fetchone()
                except sqlite3.OperationalError as exc:
                    if "no such table" not in str(exc):raise
                    row=None
                raw=row[0] if row else None
            finally:db.close()
        if old and raw==old[3]:
            item=(now,old[1],old[2],raw)
        else:
            data=json.loads(raw) if raw else None
            version=sha256((raw or "null").encode()).hexdigest()[:24]
            item=(now,data,version,raw)
        with _lock:
            # 显式失效之后，先前已在途的读取不得重新填充旧缓存。
            if epoch==_document_epoch:_documents[key]=item
        return item[1],item[2]


def invalidate_documents():
    global _document_epoch
    with _lock:
        _document_epoch+=1;_documents.clear()


def model(kind,key,builder):
    """每类独立构建；保留最近三个完整版本及同类单执行者。"""
    with _key_lock(_model_locks,kind):
        versions=_models.setdefault(kind,OrderedDict())
        if key not in versions:
            data=builder();data["snapshot_version"]=sha256(str(key).encode()).hexdigest()[:24]
            versions[key]=data
            while len(versions)>3:versions.popitem(last=False)
        return versions[key]


def versioned(kind,current,version):
    if not version or current["snapshot_version"]==version:return current
    with _key_lock(_model_locks,kind):
        for value in _models.get(kind,{}).values():
            if value["snapshot_version"]==version:return value
    raise HTTPException(409,"快照版本已更新，请刷新列表；未使用其他版本拼接结果")


def response(data,request:Request,key=None):
    """在线程内编码并复用字节，避免事件循环递归编码大字典。"""
    global _body_bytes
    cache_key=key
    with _lock:item=_bodies.get(cache_key) if cache_key else None
    if item is None:
        raw=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
        etag='W/"'+sha256(raw).hexdigest()+'"'
        compressed=gzip.compress(raw,compresslevel=1) if len(raw)>1024 else None
        item=(raw,compressed,etag)
        if cache_key:
            with _lock:
                if cache_key not in _bodies:
                    _bodies[cache_key]=item;_body_bytes+=len(raw)+len(compressed or b"")
                    while _body_bytes>32*1024*1024 and len(_bodies)>1:
                        _,removed=_bodies.popitem(last=False);_body_bytes-=len(removed[0])+len(removed[1] or b"")
    elif cache_key:
        with _lock:
            if cache_key in _bodies:_bodies.move_to_end(cache_key)
    headers={"ETag":item[2],"Vary":"Accept-Encoding","Cache-Control":"private, no-cache"}
    if item[2] in [s.strip() for s in request.headers.get("if-none-match","").split(",")]:
        return Response(status_code=304,headers=headers)
    zipped=item[1] is not None and "gzip" in request.headers.get("accept-encoding","").lower()
    if zipped:headers["Content-Encoding"]="gzip"
    return Response(item[1] if zipped else item[0],media_type="application/json",headers=headers)

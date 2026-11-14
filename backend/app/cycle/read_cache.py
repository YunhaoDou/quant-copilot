"""只读快照缓存与条件响应；不删证券、不改模拟账本。"""
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import RLock
from concurrent.futures import Future
import sys
from time import monotonic
import gzip
import json
import sqlite3
from fastapi import HTTPException, Request, Response

_lock=RLock()
_documents=OrderedDict()
_models={}
_bodies=OrderedDict()
_body_bytes=0
_document_locks={}
_model_locks={}
_document_epoch=0
_document_sizes={}
_model_sizes=OrderedDict()
_body_flights={}
_DOCUMENT_BUDGET=96*1024*1024
_MODEL_BUDGET=192*1024*1024
_BODY_BUDGET=32*1024*1024


def deep_size(value):
    """统计保留对象大小；共享对象每个条目只算一次，预算是缓存预算而非进程RSS上限。"""
    seen=set();stack=[value];total=0
    while stack:
        item=stack.pop();identity=id(item)
        if identity in seen:continue
        seen.add(identity);total+=sys.getsizeof(item)
        if isinstance(item,dict):stack.extend(item.keys());stack.extend(item.values())
        elif isinstance(item,(tuple,list,set,frozenset)):stack.extend(item)
    return total


def _trim():
    global _body_bytes
    for key in list(_document_sizes):
        if key not in _documents:_document_sizes.pop(key,None)
    for key in list(_model_sizes):
        if key[1] not in _models.get(key[0],{}):_model_sizes.pop(key,None)
    total=sum(_document_sizes.values())
    while total>_DOCUMENT_BUDGET and _documents:
        key,_=_documents.popitem(last=False);total-=_document_sizes.pop(key,0)
    total=sum(_model_sizes.values())
    while total>_MODEL_BUDGET and _model_sizes:
        (kind,key),size=_model_sizes.popitem(last=False);_models.get(kind,{}).pop(key,None);total-=size
    _body_bytes=sum(len(v[0])+len(v[1] or b'') for v in _bodies.values())
    while _body_bytes>_BODY_BUDGET and _bodies:
        _,item=_bodies.popitem(last=False);_body_bytes-=len(item[0])+len(item[1] or b'')


def configure_limits(config):
    global _DOCUMENT_BUDGET,_MODEL_BUDGET,_BODY_BUDGET
    with _lock:
        _DOCUMENT_BUDGET=int(config.get('read_cache_document_mb',96))*1024*1024
        _MODEL_BUDGET=int(config.get('read_cache_model_mb',192))*1024*1024
        _BODY_BUDGET=int(config.get('read_cache_body_mb',32))*1024*1024
        _trim()


def cache_stats():
    with _lock:
        _trim()
        return {'document_bytes':sum(_document_sizes.values()),'document_budget':_DOCUMENT_BUDGET,
                'model_bytes':sum(_model_sizes.values()),'model_budget':_MODEL_BUDGET,
                'body_bytes':_body_bytes,'body_budget':_BODY_BUDGET,
                'documents':len(_documents),'models':len(_model_sizes),'bodies':len(_bodies),'encoding_inflight':len(_body_flights)}



def _key_lock(registry,key):
    # 全局锁只保护注册表和响应LRU；IO、JSON解析及模型构建使用独立锁。
    with _lock:return registry.setdefault(key,RLock())


def document(path,table,ttl=1.):
    """完整文档最多每秒核对一次；比较原文以识别同时间戳的实际修改。"""
    key=(str(Path(path).resolve()),table)
    with _key_lock(_document_locks,key):
        with _lock:
            old=_documents.get(key);epoch=_document_epoch;old_size=_document_sizes.get(key)
        now=monotonic()
        if old and now-old[0]<ttl:
            with _lock:
                if key in _documents:_documents.move_to_end(key)
            return old[1],old[2]
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
            item=(now,old[1],old[2],old[3])
        else:
            data=json.loads(raw) if raw else None
            version=sha256((raw or "null").encode()).hexdigest()[:24]
            item=(now,data,version,raw)
        size=old_size if old and raw==old[3] and old_size is not None else deep_size(item)
        with _lock:
            # 显式失效之后，先前已在途的读取不得重新填充旧缓存。
            if epoch==_document_epoch:
                if size<=_DOCUMENT_BUDGET:
                    _documents[key]=item;_documents.move_to_end(key);_document_sizes[key]=size
                else:_documents.pop(key,None);_document_sizes.pop(key,None)
                _trim()
        return item[1],item[2]


def invalidate_documents():
    global _document_epoch
    with _lock:
        _document_epoch+=1;_documents.clear();_document_sizes.clear()


def model(kind,key,builder):
    """每类独立构建；保留最近三个完整版本及同类单执行者。"""
    with _key_lock(_model_locks,kind):
        with _lock:
            old=_models.get(kind,{}).get(key)
            if old is not None:
                if (kind,key) in _model_sizes:_model_sizes.move_to_end((kind,key))
                return old
        data=builder();data["snapshot_version"]=sha256(str(key).encode()).hexdigest()[:24]
        size=deep_size(data)
        with _lock:
            if size<=_MODEL_BUDGET:
                versions=_models.setdefault(kind,OrderedDict());versions[key]=data;_model_sizes[(kind,key)]=size
                while len(versions)>3:
                    removed,_=versions.popitem(last=False);_model_sizes.pop((kind,removed),None)
            _trim()
        return data


def versioned(kind,current,version):
    if not version or current["snapshot_version"]==version:return current
    with _lock:
        for key,value in _models.get(kind,{}).items():
            if value["snapshot_version"]==version:
                if (kind,key) in _model_sizes:_model_sizes.move_to_end((kind,key))
                return value
    raise HTTPException(409,"快照版本已更新，请刷新列表；未使用其他版本拼接结果")


def _encode(data):
    raw=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    return raw,gzip.compress(raw,compresslevel=1) if len(raw)>1024 else None,'W/"'+sha256(raw).hexdigest()+'"'


def _encoded(data,key):
    if key is None:return _encode(data)
    with _lock:
        if key in _bodies:_bodies.move_to_end(key);return _bodies[key]
        future=_body_flights.get(key);owner=future is None
        if owner:future=Future();_body_flights[key]=future
    if not owner:return future.result()
    try:
        item=_encode(data)
        with _lock:
            if len(item[0])+len(item[1] or b'')<=_BODY_BUDGET:_bodies[key]=item
            _trim();_body_flights.pop(key,None);future.set_result(item)
        return item
    except BaseException as exc:
        with _lock:_body_flights.pop(key,None);future.set_exception(exc)
        raise


def _accepts_gzip(value):
    choices={}
    for part in value.lower().split(','):
        pieces=[p.strip() for p in part.split(';')];quality=1.
        for option in pieces[1:]:
            if option.startswith('q='):
                try:quality=float(option[2:])
                except ValueError:quality=0
        choices[pieces[0]]=quality
    return 0<choices.get('gzip',choices.get('*',0))<=1


def response(data,request:Request,key=None):
    """在线程内编码并复用字节，避免事件循环递归编码大字典。"""
    item=_encoded(data,key)
    headers={"ETag":item[2],"Vary":"Accept-Encoding","Cache-Control":"private, no-cache"}
    if any(tag.strip()=="*" or tag.strip().removeprefix("W/")==item[2].removeprefix("W/") for tag in request.headers.get("if-none-match","").split(",")):
        return Response(status_code=304,headers=headers)
    zipped=item[1] is not None and _accepts_gzip(request.headers.get("accept-encoding",""))
    if zipped:headers["Content-Encoding"]="gzip"
    return Response(item[1] if zipped else item[0],media_type="application/json",headers=headers)

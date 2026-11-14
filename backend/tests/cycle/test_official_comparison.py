"""官方名单变更必须明确报告，不能靠相同总数误判为完整一致。"""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('official_verification',Path(__file__).resolve().parents[2]/'scripts/verify_official_master.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_same_count_substitution_name_change_and_duplicate_are_detected():
    old=[{'code':'600000','name':'旧名','exchange':'SH'},{'code':'000001','name':'深股','exchange':'SZ'}]
    new=[{'code':'600000','name':'新名','exchange':'SH'},{'code':'920001','name':'北股','exchange':'BJ'}]
    r=module.compare(old,new)
    assert not r['ok'] and r['newly_listed']==['BJ920001'] and r['no_longer_listed']==['SZ000001'] and r['name_changed']==['SH600000']
    assert module.compare(old,list(reversed(old)))['ok']
    with pytest.raises(ValueError):module.compare(old,old+[old[0]])

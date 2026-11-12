"""为已有vn.py源码目录安装可回滚的本地七策略桥接。"""
import argparse
from pathlib import Path
import shutil


def install(target):
    target=Path(target).expanduser().resolve()
    root=Path(__file__).resolve().parent
    if not (target/"vnpy/trader/app.py").exists() or not (target/"run_trader.py").exists():
        raise ValueError("目标不是含run_trader.py的vn.py源码目录")
    package=root/"vnpy_quant_copilot";link=target/package.name
    if link.is_symlink():
        if link.resolve()!=package:raise ValueError("已有不同的桥接链接，未覆盖")
    elif link.exists():raise ValueError("已有同名目录，未覆盖")
    else:link.symlink_to(package,target_is_directory=True)
    launcher=target/"run_trader.py";backup=target/"run_trader.before-quant-copilot.py"
    if not backup.exists():shutil.copy2(launcher,backup)
    shutil.copy2(root/"run_vnpy.py",launcher)
    return backup

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vnpy-dir",required=True)
    print("安装完成；原启动器备份：",install(parser.parse_args().vnpy_dir))

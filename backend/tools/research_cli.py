"""保留原终端的命令行诊断能力，默认A股；不自动发送通知或下单。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.research_lab import diagnose

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quant Copilot 综合诊断")
    parser.add_argument("symbol", help="六位A股代码；境外证券会单独标记来源与币种")
    parser.add_argument("--count", type=int, choices=[63, 126, 252, 504, 640], default=252)
    parser.add_argument("--capital", type=float, default=100000)
    args = parser.parse_args()
    if args.capital <= 0:
        parser.error("研究资金必须大于0")
    print(json.dumps(diagnose(args.symbol, args.count, args.capital), ensure_ascii=False, allow_nan=False))

"""CLI : python -m retrace run <feature>"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import config, steps  # noqa: F401  스텝 등록
from .driver import SeleniumDriver
from .scenario import parse_feature_file, run_scenario, save_result

MARK = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def cmd_run(args) -> int:
    feature = parse_feature_file(args.feature)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out) / run_id
    ok = True
    with SeleniumDriver(headless=not args.headed) as driver:
        for i, sc in enumerate(feature.scenarios):
            out = out_root if len(feature.scenarios) == 1 else out_root / f"{i:02d}"
            result = run_scenario(sc, driver, args.base_url, out_dir=out)
            save_result(result, out)
            print(f"[{'PASS' if result.passed else 'FAIL'}] {feature.name} / {sc.name} ({result.duration_ms}ms)")
            for r in result.steps:
                bg = " (bg)" if r.background else ""
                print(f"  {MARK[r.status]} {r.keyword} {r.text}{bg}  {r.duration_ms}ms")
                if r.error:
                    print("       " + r.error.splitlines()[0])
            print(f"  logs : console {len(result.logs['console'])} / network {len(result.logs['network'])} → {out}")
            ok &= result.passed
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="retrace")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="feature 파일 실행")
    r.add_argument("feature")
    r.add_argument("--base-url", default=config.BASE_URL)
    r.add_argument("--out", default=str(config.REPORTS_DIR))
    r.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    args = p.parse_args()
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())

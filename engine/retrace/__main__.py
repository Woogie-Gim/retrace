"""CLI : python -m retrace run|explore <feature>"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config, steps  # noqa: F401  스텝 등록
from .driver import SeleniumDriver
from .explorer import Explorer, ExploreOptions
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


def _print_steps(steps) -> None:
    for s in steps:
        mark = f"  ← 교란({s.perturbation})" if s.perturbation else ""
        print(f"      {s.keyword} {s.text}{mark}")


def cmd_explore(args) -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out) / f"explore-{run_id}"
    opts = ExploreOptions(k=args.k, max_runs=args.max_runs, collect_all=args.all, top_n=args.top)
    summary = []

    def on_event(name, data):
        if name == "baseline_start":
            print("  baseline 실행")
        elif name == "candidate_start":
            c = data["candidate"]
            print(f"  [{c.index:02d}] {'*' if c.priority else ' '} {c.kind:<11} @{c.position}  {c.label}")
        elif name == "run_done":
            hits = [f"{v.kind}: {v.detail}" for v in data["verdicts"] if v.hit]
            note = f"  {hits[0]}" if hits else ""
            if data["status"] == "invalid":
                note = f"  {data['verdicts'][0].detail}"
            print(f"       run {data['trial'] + 1}: {data['status']}{note}")

    with SeleniumDriver(headless=not args.headed) as driver:
        explorer = Explorer(driver, args.base_url, opts, on_event=on_event)
        for path in args.features:
            feature = parse_feature_file(path)
            for i, sc in enumerate(feature.scenarios):
                print(f"[explore] {feature.name} / {sc.name}")
                res = explorer.explore(sc)
                out = out_root / f"{Path(path).stem}-{i:02d}"
                out.mkdir(parents=True, exist_ok=True)
                (out / "explore.json").write_text(
                    json.dumps(res.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
                )
                for j, h in enumerate(res.hits):
                    save_result(h.result, out / f"hit-{j:02d}")
                    print(f"  HIT #{j + 1} 후보 {h.candidate.index} ({h.hits}/{h.trials})")
                    _print_steps(h.candidate.steps)
                    for v in h.verdicts:
                        print(f"      [{v.kind}{' HIT' if v.hit else ''}] {v.detail}")
                print(f"  종료 : {res.stopped} / 후보 {res.candidates} / 실행 {res.runs} → {out}")
                summary.append((f"{feature.name} / {sc.name}", res))

    print("\n요약")
    for name, res in summary:
        print(f"  {'HIT ' if res.hits else 'MISS'}  {name}  (실행 {res.runs}, {res.stopped})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="retrace")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="feature 파일 실행")
    r.add_argument("feature")
    r.add_argument("--base-url", default=config.BASE_URL)
    r.add_argument("--out", default=str(config.REPORTS_DIR))
    r.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    e = sub.add_parser("explore", help="교란 탐색")
    e.add_argument("features", nargs="+")
    e.add_argument("--base-url", default=config.BASE_URL)
    e.add_argument("--out", default=str(config.REPORTS_DIR))
    e.add_argument("--k", type=int, default=3, help="후보당 반복 횟수")
    e.add_argument("--max-runs", type=int, default=60, help="실행 예산")
    e.add_argument("--all", action="store_true", help="예산 소진까지 hit 수집")
    e.add_argument("--top", type=int, default=5, help="--all 시 상위 N개")
    e.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    args = p.parse_args()
    return cmd_explore(args) if args.cmd == "explore" else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())

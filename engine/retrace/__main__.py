"""CLI : python -m retrace run|explore|minimize|verify"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config, steps  # noqa: F401  스텝 등록
from .driver import SeleniumDriver
from .explorer import Explorer, ExploreOptions, run_clean
from .minimizer import Minimizer
from .oracle import select_oracles
from .scenario import parse_feature_file, run_scenario, save_result
from .scenario.parser import Scenario, Step
from .verifier import verify

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
    prefer = tuple(k.strip() for k in args.prefer.split(",") if k.strip())
    opts = ExploreOptions(k=args.k, max_runs=args.max_runs, collect_all=args.all, top_n=args.top, prefer=prefer)
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


def _explore_files(paths: list[str]) -> list[Path]:
    # 폴더면 하위 */explore.json, 파일이면 그대로
    out = []
    for p in map(Path, paths):
        out += sorted(p.glob("*/explore.json")) if p.is_dir() else [p]
    return out


def _load_hit(path: Path, seeds: Path) -> tuple[str, Scenario, int] | None:
    # 첫 hit 시퀀스 복원 + 폴더명(<stem>-NN)으로 시드 태그·스텝 수 조회
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data["hits"]:
        return None
    stem, _, idx = path.parent.name.rpartition("-")
    seed = parse_feature_file(seeds / f"{stem}.feature").scenarios[int(idx)]
    steps = [Step(**s) for s in data["hits"][0]["candidate"]["steps"]]
    return path.parent.name, Scenario(data["scenario"], seed.tags, steps), len(seed.steps)


def cmd_minimize(args) -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out) / f"minimize-{run_id}"
    summary = []

    def on_event(name, data):
        if name == "minimize_step":
            r = data["record"]
            note = f"  {r.detail}" if r.detail else ""
            print(f"    [{data['size']:>2}스텝] {r.outcome:<15} run {r.runs}{note}")
        elif name == "verify_progress":
            note = f"  {data['detail']}" if data["detail"] else ""
            print(f"    verify {data['trial'] + 1}/{data['total']}: {data['status']}{note}")

    with SeleniumDriver(headless=not args.headed) as driver:
        run_fn = lambda sc: run_clean(driver, args.base_url, sc)  # noqa: E731
        for path in _explore_files(args.inputs):
            loaded = _load_hit(path, Path(args.seeds))
            if loaded is None:
                print(f"[skip] hit 없음 : {path}")
                continue
            name, sc, seed_count = loaded
            oracles = select_oracles(sc.tags, driver, args.base_url)
            print(f"[minimize] {name} / {sc.name}  (시드 {seed_count} / hit {len(sc.steps)}스텝)")
            res = Minimizer(run_fn, oracles, k=args.k, on_event=on_event).minimize(sc)
            print(f"  {res.stopped} : {len(res.original)} → {len(res.minimized)}스텝 (실행 {res.runs})")
            _print_steps(res.minimized)

            report = {
                "source": str(path), "tags": sc.tags, "seed_count": seed_count,
                "minimize": res.to_dict(), "verify": None,
            }
            ver = None
            if not args.no_verify and res.stopped == "minimized":
                repro = Scenario(sc.name, sc.tags, res.minimized)
                ver = verify(repro, run_fn, oracles, n=args.verify_n,
                             expect_fixed=args.expect_fixed, on_event=on_event)
                report["verify"] = ver.to_dict()
                _print_verify(ver)

            out = out_root / name
            out.mkdir(parents=True, exist_ok=True)
            (out / "minimize.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            summary.append((name, seed_count, res, ver))

    print(f"\n요약 → {out_root}")
    for name, seed_count, res, ver in summary:
        rate = "-" if ver is None or ver.rate is None else f"{ver.rate:.0%} {ver.grade}"
        print(f"  {name:<18} 시드 {seed_count} / hit {len(res.original)} → 최소 {len(res.minimized)}  "
              f"재현율 {rate}  ({res.stopped}, 실행 {res.runs})")
    return 0


def _print_verify(ver) -> None:
    rate = "-" if ver.rate is None else f"{ver.rate:.0%}"
    fixed = "" if ver.fixed is None else f" / 수정 확인 {'OK' if ver.fixed else 'FAIL'}"
    print(f"  재현율 {rate} ({ver.hits}/{ver.hits + ver.passes}, invalid {ver.invalid}) → {ver.grade}{fixed}")


def cmd_verify(args) -> int:
    # minimize.json의 최소 스텝만 반복 실행
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out) / f"verify-{run_id}"
    paths = []
    for p in map(Path, args.inputs):
        paths += sorted(p.glob("**/minimize.json")) if p.is_dir() else [p]
    ok = True

    def on_event(name, data):
        note = f"  {data['detail']}" if data["detail"] else ""
        print(f"    verify {data['trial'] + 1}/{data['total']}: {data['status']}{note}")

    with SeleniumDriver(headless=not args.headed) as driver:
        run_fn = lambda sc: run_clean(driver, args.base_url, sc)  # noqa: E731
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            mini = data["minimize"]
            sc = Scenario(mini["scenario"], data["tags"], [Step(**s) for s in mini["minimized"]])
            name = path.parent.name
            print(f"[verify] {name} / {sc.name}  ({len(sc.steps)}스텝)")
            _print_steps(sc.steps)
            oracles = select_oracles(sc.tags, driver, args.base_url)
            ver = verify(sc, run_fn, oracles, n=args.n, expect_fixed=args.expect_fixed, on_event=on_event)
            _print_verify(ver)
            out = out_root / name
            out.mkdir(parents=True, exist_ok=True)
            (out / "verify.json").write_text(
                json.dumps({"source": str(path), **ver.to_dict()}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            ok &= ver.fixed is not False
    print(f"→ {out_root}")
    return 0 if ok else 1


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
    e.add_argument("--prefer", default="", help="맨 앞에 둘 교란 종류 (쉼표 구분, 예: network)")
    e.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    m = sub.add_parser("minimize", help="hit 시퀀스 최소화 + 재현율 검증")
    m.add_argument("inputs", nargs="+", help="explore 결과 폴더 또는 explore.json")
    m.add_argument("--base-url", default=config.BASE_URL)
    m.add_argument("--out", default=str(config.REPORTS_DIR))
    m.add_argument("--seeds", default=str(config.ROOT_DIR / "features" / "seeds"))
    m.add_argument("--k", type=int, default=3, help="후보당 반복 횟수")
    m.add_argument("--verify-n", type=int, default=10, help="검증 반복 횟수")
    m.add_argument("--no-verify", action="store_true", help="검증 생략")
    m.add_argument("--expect-fixed", action="store_true", help="BUG_MODE=off 수정 확인 (재현율 0% 기대)")
    m.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    v = sub.add_parser("verify", help="최소 스텝 재현율 검증")
    v.add_argument("inputs", nargs="+", help="minimize.json 또는 포함 폴더")
    v.add_argument("--base-url", default=config.BASE_URL)
    v.add_argument("--out", default=str(config.REPORTS_DIR))
    v.add_argument("--n", type=int, default=10, help="반복 횟수")
    v.add_argument("--expect-fixed", action="store_true", help="BUG_MODE=off 수정 확인 (재현율 0% 기대)")
    v.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    args = p.parse_args()
    cmds = {"explore": cmd_explore, "minimize": cmd_minimize, "verify": cmd_verify}
    return cmds.get(args.cmd, cmd_run)(args)


if __name__ == "__main__":
    sys.exit(main())

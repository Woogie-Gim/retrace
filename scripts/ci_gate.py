"""CI 게이트 판정 + 요약 표

사용법 (저장소 루트, engine 가상환경)
  python scripts/ci_gate.py --off off.xml --on on.xml --verify-dir reports/ci/verify

필수 게이트
  1) BUG_MODE=off : 전체 테스트 통과 (시드 4 + 생성 4 포함)
  2) BUG_MODE=on  : 시드 4건 통과
  3) BUG_MODE=on  : 확정 결함 생성 시나리오 실패
정보 표시 : 확률 결함 생성 시나리오 결과 + verify 재현율 (게이트 제외)
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from pytest_bdd.scenario import make_python_name  # noqa: E402

from retrace.scenario import parse_feature_file  # noqa: E402

SEEDS = ROOT / "features" / "seeds"
GENERATED = ROOT / "features" / "generated"
CONFIRMED = {"double_order", "empty_products"}  # 확정 100% 결함 (게이트 3)
HEADER = re.compile(r"재현율:\s*(?P<rate>[^/]+?)\s*/\s*원인 계층:\s*(?P<layer>\S+)")


def load_junit(path: Path) -> dict[str, str]:
    # 테스트 이름 → passed / failed / skipped
    out = {}
    for tc in ET.parse(path).iter("testcase"):
        status = "passed"
        if tc.find("failure") is not None or tc.find("error") is not None:
            status = "failed"
        elif tc.find("skipped") is not None:
            status = "skipped"
        out[f"{tc.get('classname')}::{tc.get('name')}"] = status
    return out


def features(folder: Path) -> list[dict]:
    # feature 파일별 pytest-bdd 테스트 이름 + 생성 헤더(기록 재현율·원인 계층)
    rows = []
    for path in sorted(folder.glob("*.feature")):
        feat = parse_feature_file(path)
        m = HEADER.search(path.read_text(encoding="utf-8-sig"))
        for sc in feat.scenarios:
            rows.append({
                "stem": path.stem,
                "defect": path.stem.rsplit("-", 1)[0],
                "title": feat.name,
                "test": f"test_{make_python_name(sc.name)}",
                "recorded_rate": m["rate"] if m else "-",
                "layer": m["layer"] if m else "-",
            })
    return rows


def status_of(junit: dict[str, str], module: str, test: str) -> str:
    hits = [s for k, s in junit.items() if k.endswith(f"{module}::{test}")]
    return hits[0] if len(hits) == 1 else "missing"


def latest_verify(folder: Path | None) -> dict[str, dict]:
    # 이름별 가장 최근 verify.json
    out = {}
    if folder and folder.exists():
        for p in sorted(folder.glob("**/verify.json")):
            out[p.parent.name] = json.loads(p.read_text(encoding="utf-8"))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="CI 게이트 판정")
    p.add_argument("--off", type=Path, required=True, help="BUG_MODE=off junit xml")
    p.add_argument("--on", type=Path, required=True, help="BUG_MODE=on junit xml")
    p.add_argument("--verify-dir", type=Path, help="확률 결함 verify 결과 폴더")
    args = p.parse_args()

    off, on = load_junit(args.off), load_junit(args.on)
    seeds, generated = features(SEEDS), features(GENERATED)
    verify = latest_verify(args.verify_dir)
    gates: list[tuple[str, bool, str]] = []

    # 게이트 1 : off 전체 통과 + 시드·생성 시나리오 누락 없음
    off_bad = [k for k, s in off.items() if s != "passed"]
    off_missing = [r["stem"] for r in seeds + generated
                   if status_of(off, "test_seeds" if r in seeds else "test_generated", r["test"]) == "missing"]
    gates.append(("1. off : 전체 통과", not off_bad and not off_missing,
                  f"{len(off) - len(off_bad)}/{len(off)} passed" + (f", 누락 {off_missing}" if off_missing else "")))

    # 게이트 2 : on 시드 통과
    seed_st = {r["stem"]: status_of(on, "test_seeds", r["test"]) for r in seeds}
    gates.append(("2. on : 시드 통과", len(seed_st) == 4 and all(s == "passed" for s in seed_st.values()),
                  ", ".join(f"{k} {v}" for k, v in seed_st.items())))

    # 게이트 3 : on 확정 결함 생성 시나리오 실패
    gen_st = {r["defect"]: status_of(on, "test_generated", r["test"]) for r in generated}
    conf_st = {d: gen_st.get(d, "missing") for d in sorted(CONFIRMED)}
    gates.append(("3. on : 확정 결함 실패", all(s == "failed" for s in conf_st.values()),
                  ", ".join(f"{k} {v}" for k, v in conf_st.items())))

    # 요약 표
    lines = ["## Retrace 회귀 게이트", "", "| 게이트 | 결과 | 상세 |", "|---|---|---|"]
    lines += [f"| {name} | {'✅ PASS' if ok else '❌ FAIL'} | {detail} |" for name, ok, detail in gates]
    lines += [
        "", "## 결함별 결과 (BUG_MODE=on)", "",
        "| 결함 | 구분 | 생성 시나리오 (on) | 재현율 (이번 실행) | 재현율 (생성 시 기록) | 원인 계층 (생성 시 기록) |",
        "|---|---|---|---|---|---|",
    ]
    for r in generated:
        gate = r["defect"] in CONFIRMED
        v = verify.get(r["stem"])
        if gate:
            measured = "게이트 (1회 실행)"
        elif v and v.get("rate") is not None:
            measured = f"{v['rate']:.0%} ({v['hits']}/{v['hits'] + v['passes']}, invalid {v['invalid']})"
        else:
            measured = "미측정"
        lines.append(f"| {r['title']} | {'필수 게이트' if gate else '정보 표시'} | {gen_st.get(r['defect'])} "
                     f"| {measured} | {r['recorded_rate']} | {r['layer']} |")
    lines += ["", "- 원인 계층은 생성 `.feature` 헤더의 기록값이며 이번 실행에서 다시 분류하지 않았습니다",
              "- 확률 결함은 실행에 따라 통과할 수 있어 게이트에서 제외합니다"]
    md = "\n".join(lines) + "\n"

    print(md)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    return 0 if all(ok for _, ok, _ in gates) else 1


if __name__ == "__main__":
    sys.exit(main())

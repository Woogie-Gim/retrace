"""시드·리포트 조회 (파일시스템 읽기 전용)"""
import json
from dataclasses import asdict
from pathlib import Path

from ..scenario.parser import Scenario, parse_feature_file


def _symptom(description: str) -> str:
    text = " ".join(l for l in description.splitlines() if l)
    return text.split(":", 1)[1].strip() if text.startswith("증상") and ":" in text else text


def list_scenarios(seeds_dir: Path) -> list[dict]:
    # 시나리오마다 id = <stem>-NN
    out = []
    for path in sorted(Path(seeds_dir).glob("*.feature")):
        feature = parse_feature_file(path)
        source = path.read_text(encoding="utf-8-sig")
        for i, sc in enumerate(feature.scenarios):
            out.append({
                "id": f"{path.stem}-{i:02d}",
                "file": path.name,
                "feature": feature.name,
                "symptom": _symptom(feature.description),
                "scenario": sc.name,
                "tags": sc.tags,
                "steps": [asdict(s) for s in sc.steps],
                "source": source,
            })
    return out


def find_scenario(seeds_dir: Path, scenario_id: str) -> Scenario | None:
    stem, _, idx = scenario_id.rpartition("-")
    path = Path(seeds_dir) / f"{stem}.feature"
    if not stem or not idx.isdigit() or not path.is_file():
        return None
    scenarios = parse_feature_file(path).scenarios
    return scenarios[int(idx)] if int(idx) < len(scenarios) else None


def _report_id(path: Path, reports_dir: Path) -> str:
    return path.parent.relative_to(reports_dir).as_posix()


def list_reports(reports_dir: Path) -> list[dict]:
    # reports/<실행>/<이름>/report.json 요약, 최신순
    reports_dir = Path(reports_dir)
    out = []
    for path in reports_dir.glob("*/*/report.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        verify = data.get("verify") or {}
        out.append({
            "id": _report_id(path, reports_dir),
            "name": data.get("name"),
            "feature": data.get("feature"),
            "symptom": data.get("symptom"),
            "created_at": data.get("created_at"),
            "verify": {"rate": verify.get("rate"), "grade": verify.get("grade")},
            "cause": (data.get("cause") or {}).get("layer"),
            "counts": data.get("counts"),
        })
    out.sort(key=lambda r: (r["created_at"] or "", r["id"]), reverse=True)
    return out


def load_report(reports_dir: Path, report_id: str) -> dict | None:
    # 경로 탈출 방지
    reports_dir = Path(reports_dir).resolve()
    path = (reports_dir / report_id / "report.json").resolve()
    if reports_dir not in path.parents or not path.is_file():
        return None
    return {"id": _report_id(path, reports_dir), **json.loads(path.read_text(encoding="utf-8"))}

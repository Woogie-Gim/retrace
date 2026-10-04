"""리포터 : 최소 재현 결과 → 증거 run → repro.feature / report.md / report.json / evidence/"""
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .. import config
from ..oracle import Oracle, Verdict, failed_keyword
from ..oracle.dom import effective_keywords
from ..scenario.parser import Scenario, Step, parse_feature_file
from ..scenario.registry import StepRegistry, registry as default_registry
from ..scenario.runner import RunResult, save_result
from .cause import UNKNOWN, Cause, classify
from .render import format_feature, render_md

DEFAULT_WINDOW = "1280x800"


@dataclass
class Repro:
    name: str               # <시드 stem>-NN
    source: str             # minimize.json 경로
    feature: str
    description: list[str]  # 시드 feature 설명 (증상)
    scenario: str
    tags: list[str]
    steps: list[Step]
    seed_count: int
    hit_count: int
    verify: dict | None

    @property
    def symptom(self) -> str:
        text = " ".join(self.description)
        return text.split(":", 1)[1].strip() if text.startswith("증상") and ":" in text else text

    def as_scenario(self) -> Scenario:
        return Scenario(self.scenario, self.tags, self.steps)


def _rel(path: Path | str, base: Path = config.ROOT_DIR) -> str:
    p = Path(path).resolve()
    try:
        return p.relative_to(base.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def load_repro(path: str | Path, seeds_dir: str | Path) -> Repro | None:
    # 최소화 성공 결과만 대상, 폴더명(<stem>-NN)으로 시드 조회
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    mini = data["minimize"]
    if mini["stopped"] != "minimized":
        return None
    name = path.parent.name
    stem, _, idx = name.rpartition("-")
    feature = parse_feature_file(Path(seeds_dir) / f"{stem}.feature")
    seed = feature.scenarios[int(idx)]
    return Repro(
        name=name,
        source=_rel(path),
        feature=feature.name,
        description=[l for l in feature.description.splitlines() if l],
        scenario=seed.name,
        tags=data.get("tags") or seed.tags,
        steps=[Step(**s) for s in mini["minimized"]],
        seed_count=data.get("seed_count", len(seed.steps)),
        hit_count=mini.get("original_count", len(mini["original"])),
        verify=data.get("verify"),
    )


def pick_latest(paths: list[Path]) -> list[Path]:
    # 이름별 최신(minimize-<시각> 정렬) 최소화 성공 결과
    latest: dict[str, Path] = {}
    for p in sorted(paths, key=lambda p: (p.parent.parent.name, str(p))):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data["minimize"]["stopped"] == "minimized":
            latest[p.parent.name] = p
    return [latest[k] for k in sorted(latest)]


def _judge(result: RunResult, oracles: list[Oracle], kinds: set[str]) -> tuple[str, list[Verdict]]:
    # hit 판정은 태그 활성 오라클만, verdict는 원인 분류용으로 전체 수집
    kw = failed_keyword(result)
    if kw is not None and kw != "Then":
        return "invalid", []
    verdicts = [v for o in oracles if (v := o.check(result)) is not None]
    return ("hit" if any(v.hit and v.kind in kinds for v in verdicts) else "pass"), verdicts


def _network_profile(steps: list[Step], registry: StepRegistry) -> str:
    profile = "fast"
    for s in steps:
        if s.perturbation == "network":
            profile = registry.match(s.text)[1].get("profile", profile)
    return profile


def _first_line(text: str | None) -> str:
    line = (text or "").splitlines()[0] if text else ""
    return line.split(": ", 1)[1] if line.startswith("AssertionError: ") else line


def _actual(status: str, result: RunResult, verdicts: list[Verdict]) -> str:
    if status != "hit":
        return f"증거 run 미적중 ({status})"
    parts = []
    if result.failed_at is not None:
        parts.append(_first_line(result.steps[result.failed_at].error))
    parts += [f"{v.kind}: {v.detail}" for v in verdicts if v.hit and v.kind != "dom"]
    api = next((v for v in verdicts if v.kind == "api" and not v.hit), None)
    if api:
        parts.append(f"API 비교: {api.detail}")
    return " / ".join(parts)


def build_report(
    repro: Repro,
    run_fn: Callable[[Scenario, Path], RunResult],
    oracles: list[Oracle],
    selected_kinds: set[str],
    out_dir: str | Path,
    generated_dir: str | Path | None = None,
    driver_info: Callable[[], dict] | None = None,
    tries: int = 10,
    registry: StepRegistry | None = None,
    on_event: Callable[[str, dict], None] | None = None,
) -> dict:
    registry = registry or default_registry
    on_event = on_event or (lambda name, data: None)
    out = Path(out_dir)
    evidence = out / "evidence"

    # 증거 run : hit까지 반복, 매 시도 evidence 초기화
    status, verdicts, result, used = "pass", [], None, 0
    for i in range(max(tries, 1)):
        shutil.rmtree(evidence, ignore_errors=True)
        result = run_fn(repro.as_scenario(), evidence)
        status, verdicts = _judge(result, oracles, selected_kinds)
        used = i + 1
        on_event("evidence_run", {"trial": i, "total": tries, "status": status})
        if status == "hit":
            break
    save_result(result, evidence)
    info = driver_info() if driver_info else {}

    cause = classify(verdicts, result.logs) if status == "hit" else Cause(UNKNOWN, f"증거 run 미적중 ({used}회)")
    eff = effective_keywords([s.keyword for s in repro.steps])
    ver = repro.verify or {"runs": 0, "hits": 0, "passes": 0, "invalid": 0, "rate": None, "grade": "-"}
    rate = "-" if ver["rate"] is None else f"{ver['rate']:.0%}"

    feature_text = format_feature(
        repro.feature,
        f"{repro.scenario} (최소 재현)",
        repro.steps,
        tags=repro.tags,
        description=[*repro.description, f"재현율: {rate} ({ver['grade']}) / 원인 계층: {cause.layer}"],
        header=["Retrace 생성 최소 재현 시나리오", f"원본 : {repro.source}"],
    )
    generated = None
    out.mkdir(parents=True, exist_ok=True)
    (out / "repro.feature").write_text(feature_text, encoding="utf-8")
    if generated_dir is not None:
        gen = Path(generated_dir) / f"{repro.name}.feature"
        gen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out / "repro.feature", gen)
        generated = _rel(gen)

    report = {
        "name": repro.name,
        "feature": repro.feature,
        "symptom": repro.symptom,
        "scenario": repro.scenario,
        "tags": repro.tags,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "verify": {k: v for k, v in ver.items() if k != "attempts"},
        "counts": {"seed": repro.seed_count, "hit": repro.hit_count, "minimized": len(repro.steps)},
        "steps": [asdict(s) for s in repro.steps],
        "expected": " / ".join(s.text for s, k in zip(repro.steps, eff) if k == "Then"),
        "actual": _actual(status, result, verdicts),
        "cause": cause.to_dict(),
        "verdicts": [asdict(v) for v in verdicts],
        "environment": {
            "browser": info.get("browser"),
            "window": info.get("window") or DEFAULT_WINDOW,
            "network": _network_profile(repro.steps, registry),
        },
        "evidence": {
            "status": status,
            "tries": used,
            "screenshots": [
                {"index": r.index, "text": r.text, "path": _rel(r.screenshot, out)}
                for r in result.steps if r.screenshot
            ],
            "console": "evidence/console.json",
            "network": "evidence/network.json",
            "result": "evidence/result.json",
        },
        "source": repro.source,
        "generated": generated,
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_md(report), encoding="utf-8")
    return report

"""출력 렌더링 : repro.feature / report.md"""
from ..oracle.dom import effective_keywords
from ..scenario.parser import Step

PERTURB_MARK = "← 탐색으로 찾은 교란"


def _keywords(steps: list[Step]) -> list[str]:
    # 주 키워드가 바뀔 때만 Given/When/Then, 나머지 And
    out, prev = [], None
    for k in effective_keywords([s.keyword for s in steps]):
        out.append("And" if k == prev else k)
        prev = k
    return out


def _step_lines(steps: list[Step], indent: str) -> list[str]:
    lines = []
    for kw, s in zip(_keywords(steps), steps):
        if s.perturbation:
            lines.append(f"{indent}# 교란({s.perturbation})")
        lines.append(f"{indent}{kw} {s.text}")
    return lines


def format_feature(
    name: str,
    scenario: str,
    steps: list[Step],
    tags: list[str] | None = None,
    description: list[str] | None = None,
    header: list[str] | None = None,
) -> str:
    background = [s for s in steps if s.background]
    body = [s for s in steps if not s.background]
    lines = [f"# {h}" for h in header or []]
    if tags:
        lines.append(" ".join(tags))
    lines.append(f"Feature: {name}")
    lines += [f"  {d}" for d in description or []]
    if background:
        lines += ["", "  Background:", *_step_lines(background, "    ")]
    lines += ["", f"  Scenario: {scenario}", *_step_lines(body, "    ")]
    return "\n".join(lines) + "\n"


def _rate(report: dict) -> str:
    rate = report["verify"]["rate"]
    return "-" if rate is None else f"{rate:.0%}"


def render_md(report: dict) -> str:
    env, cause, ev = report["environment"], report["cause"], report["evidence"]
    steps = [Step(**s) for s in report["steps"]]
    pre = [s for s in steps if s.background]
    eff = effective_keywords([s.keyword for s in steps])
    actions = [s for s, k in zip(steps, eff) if not s.background and k != "Then"]

    lines = [
        f"## [{report['verify']['grade']} {_rate(report)}] {report['feature']}",
        "",
        f"- 환경 : {env.get('browser') or '-'} / {env.get('window') or '-'} / {env.get('network')}",
        f"- 원인 계층 : {cause['layer']} ({cause['reason']})",
        f"- 사전 조건 : {', '.join(s.text for s in pre) or '-'}",
        f"- 증상 : {report['symptom'] or '-'}",
        f"- 재현율 : {_rate(report)} ({report['verify']['hits']}/{report['verify']['hits'] + report['verify']['passes']}, "
        f"invalid {report['verify']['invalid']}) / 스텝 수 시드 {report['counts']['seed']} / hit {report['counts']['hit']} → 최소 {report['counts']['minimized']}",
        "",
        "### 재현 스텝",
    ]
    for i, s in enumerate(actions, 1):
        lines.append(f"{i}. {s.text}" + (f"   {PERTURB_MARK} ({s.perturbation})" if s.perturbation else ""))
    lines += ["", "### 기대 결과", report["expected"] or "-", "", "### 실제 결과", report["actual"] or "-"]
    lines += ["", "### 증거", f"- 증거 run : {ev['status']} ({ev['tries']}회 시도)"]
    for shot in ev["screenshots"]:
        lines.append(f"- 스크린샷 {shot['index']:02d} : [{shot['text']}]({shot['path']})")
    lines += [
        f"- 콘솔 로그 : [{ev['console']}]({ev['console']})",
        f"- 네트워크 로그 : [{ev['network']}]({ev['network']})",
        f"- 실행 결과 : [{ev['result']}]({ev['result']})",
    ]
    return "\n".join(lines) + "\n"

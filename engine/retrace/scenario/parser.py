"""feature 파싱 : gherkin-official AST → Step 리스트"""
from dataclasses import dataclass, field
from pathlib import Path

from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner


@dataclass
class Step:
    keyword: str        # Given / When / Then / And / But
    text: str
    line: int = 0
    background: bool = False  # 교란 삽입·제거 제외 대상
    perturbation: str | None = None  # 탐색기가 삽입한 교란 종류


@dataclass
class Scenario:
    name: str
    tags: list[str] = field(default_factory=list)  # feature + scenario 태그
    steps: list[Step] = field(default_factory=list)  # Background 스텝 선행 병합


@dataclass
class Feature:
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    path: str | None = None


def _steps(nodes: list[dict], background: bool) -> list[Step]:
    return [
        Step(n["keyword"].strip(), n["text"], n["location"]["line"], background)
        for n in nodes
    ]


def _tags(node: dict) -> list[str]:
    return [t["name"] for t in node.get("tags", [])]


def parse_feature(text: str, path: str | None = None) -> Feature:
    doc = Parser().parse(TokenScanner(text))
    feat = doc.get("feature")
    if not feat:
        raise ValueError(f"Feature 없음: {path or '<text>'}")

    feature = Feature(
        name=feat["name"],
        description="\n".join(l.strip() for l in feat.get("description", "").splitlines()).strip(),
        tags=_tags(feat),
        path=path,
    )
    background: list[Step] = []
    for child in feat["children"]:
        if "background" in child:
            background = _steps(child["background"]["steps"], background=True)
        elif "scenario" in child:
            sc = child["scenario"]
            if sc.get("examples"):
                raise NotImplementedError(f"Scenario Outline 미지원: {sc['name']}")
            feature.scenarios.append(Scenario(
                name=sc["name"],
                tags=feature.tags + _tags(sc),
                steps=[*background, *_steps(sc["steps"], background=False)],
            ))
        elif "rule" in child:
            raise NotImplementedError("Rule 미지원")
    return feature


def parse_feature_file(path: str | Path) -> Feature:
    path = Path(path)
    # BOM 포함 파일 허용 (윈도우 편집기)
    return parse_feature(path.read_text(encoding="utf-8-sig"), str(path))

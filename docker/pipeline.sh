#!/bin/sh
# 탐색 → 최소화(+검증) → 리포트 일괄 실행
# 사용법 : sh docker/pipeline.sh <seed.feature>... (engine 컨테이너, /app/engine 기준)
# 환경변수 : VERIFY_N(검증 반복, 기본 3) / EXPLORE_MAX_RUNS(탐색 예산, 기본 60)
set -eu

if [ "$#" -eq 0 ]; then
  echo "usage: sh docker/pipeline.sh <seed.feature>..." >&2
  exit 2
fi

# 실행별 출력 폴더 분리
OUT="${RETRACE_REPORTS_DIR:-/app/reports}/pipeline-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
cd /app/engine

# 상대 경로 시드는 /app 기준
SEEDS=""
for f in "$@"; do
  case "$f" in /*) SEEDS="$SEEDS $f" ;; *) SEEDS="$SEEDS /app/$f" ;; esac
done

echo "== [1/3] explore → $OUT"
# shellcheck disable=SC2086
python -m retrace explore $SEEDS --out "$OUT" --max-runs "${EXPLORE_MAX_RUNS:-60}"
EXPLORE_DIR=$(ls -d "$OUT"/explore-* | tail -n 1)

echo "== [2/3] minimize + verify(${VERIFY_N:-3}회) ← $EXPLORE_DIR"
python -m retrace minimize "$EXPLORE_DIR" --out "$OUT" --verify-n "${VERIFY_N:-3}"
MINIMIZE_DIR=$(ls -d "$OUT"/minimize-* | tail -n 1)

echo "== [3/3] report ← $MINIMIZE_DIR"
python -m retrace report "$MINIMIZE_DIR" --out "$OUT" --generated "$OUT/generated"

echo "== 완료 : $OUT"
ls "$OUT"/report-*/*/report.json

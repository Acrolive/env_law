#!/usr/bin/env python3
"""Deterministic run-state gate shared by Claude and Codex harnesses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


MAX_ITERATIONS = 4
ACCEPTANCE_SCORE = 90.0
SCHEMA_VERSION = 1
JSON_STAGES = {"researcher", "verifier", "evaluation"}
ALL_STAGES = JSON_STAGES | {"draft"}
OC_PATTERNS = (
    re.compile(r"(?:[?&]|^)OC(?:=|%3D)([^&\s\"'<>]+)", re.IGNORECASE),
    re.compile(r"(?:LAW_API_)?OC\s*[:=]\s*[\"']?([^,}\s\"']+)", re.IGNORECASE),
)
MASKED_OC_VALUES = {"<OC>", "%3COC%3E", "***", "REDACTED"}


class ContractError(ValueError):
    pass


@lru_cache(maxsize=1)
def configured_oc() -> str:
    value = os.environ.get("LAW_API_OC", "")
    if value:
        return value
    project_root = Path(__file__).resolve().parents[1]
    loader = project_root / "scripts" / "load_law_env.sh"
    env_file = project_root / ".env"
    if not loader.is_file() or not env_file.is_file():
        return ""
    command = 'source "$1"; load_law_env "$2"; printf %s "${LAW_API_OC:-}"'
    result = subprocess.run(
        ["bash", "-c", command, "--", str(loader), str(env_file)],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"JSON을 읽을 수 없음: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"최상위 JSON은 객체여야 함: {path}")
    return value


def require_fields(data: dict[str, Any], fields: dict[str, type], stage: str) -> None:
    for key, expected in fields.items():
        if key not in data:
            raise ContractError(f"{stage}: 필수 필드 누락: {key}")
        if expected is int and isinstance(data[key], bool):
            raise ContractError(f"{stage}: {key} 타입은 int여야 함")
        if not isinstance(data[key], expected):
            if isinstance(expected, tuple):
                expected_name = " 또는 ".join(item.__name__ for item in expected)
            else:
                expected_name = expected.__name__
            raise ContractError(f"{stage}: {key} 타입은 {expected_name}이어야 함")


def validate_no_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() == "law_api_oc":
                raise ContractError(f"비밀 필드 금지: {path}.{key}")
            validate_no_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_no_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str):
        secret = configured_oc()
        if secret and secret in value:
            raise ContractError(f"설정된 OC가 포함됨: {path}")
        for pattern in OC_PATTERNS:
            for match in pattern.finditer(value):
                if match.group(1).upper() not in MASKED_OC_VALUES:
                    raise ContractError(f"마스킹되지 않은 OC가 포함됨: {path}")


def validate_iteration(data: dict[str, Any], expected_iteration: int, stage: str) -> None:
    iteration = data.get("iteration")
    if iteration != expected_iteration:
        raise ContractError(f"{stage}: iteration={iteration!r}, 예상값={expected_iteration}")


def validate_researcher(data: dict[str, Any], iteration: int) -> None:
    require_fields(
        data,
        {
            "iteration": int,
            "queries_executed": list,
            "evidence": dict,
            "self_critique": dict,
            "stop_reason": str,
        },
        "researcher",
    )
    validate_iteration(data, iteration, "researcher")


def validate_verifier(data: dict[str, Any], iteration: int) -> None:
    require_fields(
        data,
        {
            "iteration": int,
            "verified": bool,
            "checked": int,
            "passed": int,
            "failed": list,
            "warnings": list,
            "evidence": dict,
        },
        "verifier",
    )
    validate_iteration(data, iteration, "verifier")
    if data["checked"] < 0 or data["passed"] < 0:
        raise ContractError("verifier: checked/passed는 음수일 수 없음")
    if data["checked"] != data["passed"] + len(data["failed"]):
        raise ContractError("verifier: checked는 passed + failed 개수와 같아야 함")
    if data["verified"] != (len(data["failed"]) == 0):
        raise ContractError("verifier: verified는 failed가 비어 있는지와 일치해야 함")


def validate_evaluation(data: dict[str, Any], iteration: int, acceptance_score: float) -> None:
    require_fields(
        data,
        {
            "iteration": int,
            "scores": dict,
            "mean": (int, float),
            "accepted": bool,
            "details": list,
            "must_fix": list,
        },
        "evaluation",
    )
    validate_iteration(data, iteration, "evaluation")
    score_values = []
    for key in ("official", "expert", "operator"):
        value = data["scores"].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractError(f"evaluation: scores.{key}는 숫자여야 함")
        if not 0 <= float(value) <= 100:
            raise ContractError(f"evaluation: scores.{key}는 0~100이어야 함")
        score_values.append(float(value))
    expected_mean = sum(score_values) / len(score_values)
    if abs(float(data["mean"]) - expected_mean) > 0.05:
        raise ContractError(
            f"evaluation: mean={data['mean']}은 산술평균 {expected_mean:.2f}와 일치하지 않음"
        )
    expected_accepted = expected_mean >= acceptance_score
    if data["accepted"] != expected_accepted:
        raise ContractError(
            f"evaluation: accepted는 mean >= {acceptance_score:g}와 일치해야 함"
        )
    if data["accepted"] and data["must_fix"]:
        raise ContractError("evaluation: accepted=true이면 must_fix가 비어 있어야 함")


def validate_stage(stage: str, data: dict[str, Any], iteration: int, acceptance_score: float) -> None:
    validate_no_secrets(data)
    if stage == "researcher":
        validate_researcher(data, iteration)
    elif stage == "verifier":
        validate_verifier(data, iteration)
    elif stage == "evaluation":
        validate_evaluation(data, iteration, acceptance_score)
    else:
        raise ContractError(f"알 수 없는 JSON 단계: {stage}")


def manifest_path(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def load_manifest(run_dir: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path(run_dir))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("지원하지 않는 manifest schema_version")
    if manifest.get("max_iterations") != MAX_ITERATIONS:
        raise ContractError("manifest max_iterations 계약 불일치")
    if not isinstance(manifest.get("stages"), dict):
        raise ContractError("manifest stages는 객체여야 함")
    return manifest


def stage_map(manifest: dict[str, Any], iteration: int) -> dict[str, str]:
    value = manifest["stages"].setdefault(str(iteration), {})
    if not isinstance(value, dict):
        raise ContractError(f"manifest stages.{iteration}은 객체여야 함")
    return value


def ensure_record_order(manifest: dict[str, Any], iteration: int, stage: str) -> None:
    current = stage_map(manifest, iteration)
    if stage == "researcher":
        if iteration > 1:
            previous = stage_map(manifest, iteration - 1)
            if "verifier" not in previous and "evaluation" not in previous:
                raise ContractError("다음 researcher 전에 이전 verifier 또는 evaluation이 필요함")
        return
    if "researcher" not in current:
        raise ContractError(f"{stage} 전에 같은 반복의 researcher가 필요함")
    if stage == "verifier":
        return
    if "verifier" not in current:
        raise ContractError(f"{stage} 전에 같은 반복의 verifier가 필요함")


def read_recorded_json(run_dir: Path, relative_path: str) -> dict[str, Any]:
    return read_json(run_dir / relative_path)


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{timestamp}-{secrets.token_hex(4)}"
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise ContractError("run-id는 영문, 숫자, 점, 밑줄, 하이픈만 허용")
    run_dir = root / run_id
    if run_dir.exists():
        raise ContractError(f"실행 디렉터리가 이미 존재함: {run_dir}")

    query_sha256 = None
    if args.query_file:
        query_bytes = Path(args.query_file).read_bytes()
        query_sha256 = hashlib.sha256(query_bytes).hexdigest()

    now = utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "max_iterations": MAX_ITERATIONS,
        "acceptance_score": ACCEPTANCE_SCORE,
        "current_iteration": 0,
        "query_sha256": query_sha256,
        "stages": {},
    }
    atomic_write(manifest_path(run_dir), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(run_dir)
    return 0


def command_record(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = validate_run(run_dir)
    if manifest["status"] != "active":
        raise ContractError("종료된 실행에는 단계를 기록할 수 없음")
    if not 1 <= args.iteration <= manifest["max_iterations"]:
        raise ContractError(f"iteration은 1~{manifest['max_iterations']} 범위여야 함")
    if args.stage not in ALL_STAGES:
        raise ContractError(f"지원하지 않는 단계: {args.stage}")

    if args.iteration > 1 and args.stage == "researcher":
        previous = manifest["stages"].get(str(args.iteration - 1))
        if not isinstance(previous, dict):
            raise ContractError("반복 번호를 건너뛸 수 없음")
        evaluation_path = previous.get("evaluation")
        if evaluation_path:
            previous_evaluation = read_recorded_json(run_dir, evaluation_path)
            if previous_evaluation.get("accepted"):
                raise ContractError("accepted 평가 뒤에는 새 반복을 시작할 수 없음")

    ensure_record_order(manifest, args.iteration, args.stage)
    current = stage_map(manifest, args.iteration)
    if args.stage in current and not args.replace:
        raise ContractError("이미 기록된 단계임; 교체하려면 --replace 사용")
    if args.replace:
        dependent_stages = {
            "researcher": {"verifier", "draft", "evaluation"},
            "verifier": {"draft", "evaluation"},
            "draft": {"evaluation"},
            "evaluation": set(),
        }[args.stage]
        present_dependents = sorted(dependent_stages.intersection(current))
        if present_dependents:
            raise ContractError(
                f"후속 단계가 있어 {args.stage}를 교체할 수 없음: {', '.join(present_dependents)}"
            )

    input_path = Path(args.input)
    suffix = ".md" if args.stage == "draft" else ".json"
    relative_path = Path(f"iteration-{args.iteration}") / f"{args.stage}{suffix}"
    destination = run_dir / relative_path

    if args.stage == "draft":
        content = input_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ContractError("draft는 비어 있을 수 없음")
        verifier = read_recorded_json(run_dir, current["verifier"])
        if not verifier.get("verified"):
            raise ContractError("verifier가 거부한 반복에는 draft를 기록할 수 없음")
        validate_no_secrets(content)
        atomic_write(destination, content.rstrip() + "\n")
    else:
        data = read_json(input_path)
        validate_stage(args.stage, data, args.iteration, float(manifest["acceptance_score"]))
        if args.stage == "evaluation":
            verifier = read_recorded_json(run_dir, current["verifier"])
            if not verifier.get("verified") or "draft" not in current:
                raise ContractError("evaluation 전에 통과 verifier와 draft가 필요함")
        atomic_write(destination, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    current[args.stage] = relative_path.as_posix()
    manifest["current_iteration"] = max(manifest["current_iteration"], args.iteration)
    manifest["updated_at"] = utc_now()
    atomic_write(manifest_path(run_dir), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(destination)
    return 0


def validate_run(run_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(run_dir)
    acceptance_score = float(manifest["acceptance_score"])
    ordered_stages = sorted(manifest["stages"].items(), key=lambda item: int(item[0]))
    accepted_iteration = None
    previous_records: dict[str, str] | None = None
    previous_iteration = 0
    max_recorded_iteration = 0
    for iteration_text, records in ordered_stages:
        iteration = int(iteration_text)
        max_recorded_iteration = max(max_recorded_iteration, iteration)
        if not 1 <= iteration <= manifest["max_iterations"]:
            raise ContractError(f"manifest iteration 범위 오류: {iteration}")
        if not isinstance(records, dict):
            raise ContractError(f"stages.{iteration}은 객체여야 함")
        if iteration > 1 and "researcher" in records:
            if iteration != previous_iteration + 1:
                raise ContractError(f"iteration 번호가 연속적이지 않음: {previous_iteration} → {iteration}")
            if previous_records is None or not ({"verifier", "evaluation"} & previous_records.keys()):
                raise ContractError(f"iteration {iteration} researcher의 이전 단계가 없음")
        if "verifier" in records and "researcher" not in records:
            raise ContractError(f"iteration {iteration} verifier 전에 researcher가 없음")
        if "draft" in records and "verifier" not in records:
            raise ContractError(f"iteration {iteration} draft 전에 verifier가 없음")
        if "evaluation" in records and not {"verifier", "draft"}.issubset(records):
            raise ContractError(f"iteration {iteration} evaluation 전에 verifier/draft가 없음")
        if accepted_iteration is not None:
            raise ContractError(f"accepted iteration {accepted_iteration} 뒤에 단계가 기록됨")

        expected_prefix = f"iteration-{iteration}/"
        for stage, relative_path in records.items():
            if stage not in ALL_STAGES or not isinstance(relative_path, str):
                raise ContractError(f"잘못된 단계 레코드: {iteration}/{stage}")
            if not relative_path.startswith(expected_prefix):
                raise ContractError(f"단계 경로가 iteration과 일치하지 않음: {relative_path}")
            path = (run_dir / relative_path).resolve()
            if run_dir not in path.parents:
                raise ContractError(f"실행 디렉터리를 벗어난 단계 경로: {relative_path}")
            if not path.is_file():
                raise ContractError(f"단계 파일 누락: {path}")
            if stage == "draft":
                content = path.read_text(encoding="utf-8")
                if not content.strip():
                    raise ContractError(f"빈 draft: {path}")
                validate_no_secrets(content)
            else:
                stage_data = read_json(path)
                validate_stage(stage, stage_data, iteration, acceptance_score)
                if stage == "verifier" and not stage_data["verified"]:
                    if "draft" in records or "evaluation" in records:
                        raise ContractError(f"iteration {iteration}의 거부 verifier 뒤에 후속 단계가 있음")
                if stage == "evaluation" and stage_data["accepted"]:
                    accepted_iteration = iteration
        previous_records = records
        previous_iteration = iteration
    if manifest["current_iteration"] != max_recorded_iteration:
        raise ContractError("manifest current_iteration이 기록된 단계와 일치하지 않음")
    return manifest


def command_validate(args: argparse.Namespace) -> int:
    manifest = validate_run(Path(args.run_dir).resolve())
    print(json.dumps({"valid": True, "run_id": manifest["run_id"]}, ensure_ascii=False))
    return 0


def command_finish(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = validate_run(run_dir)
    if manifest["status"] != "active":
        raise ContractError("이미 종료된 실행임")

    evaluations = []
    verifier_failures = []
    for iteration_text, records in manifest["stages"].items():
        if "evaluation" in records:
            evaluations.append(read_recorded_json(run_dir, records["evaluation"]))
        if "verifier" in records:
            verifier = read_recorded_json(run_dir, records["verifier"])
            verifier_failures.append(not verifier["verified"])

    if args.status == "accepted" and not any(item["accepted"] for item in evaluations):
        raise ContractError("accepted 평가는 없으므로 accepted로 종료할 수 없음")
    if args.status == "partial":
        if manifest["current_iteration"] < MAX_ITERATIONS:
            raise ContractError("partial은 최대 반복에 도달한 뒤에만 허용")
        if not evaluations:
            raise ContractError("partial은 적어도 한 번의 evaluation이 있어야 함")
        if any(item["accepted"] for item in evaluations):
            raise ContractError("accepted 평가가 있으면 partial로 종료할 수 없음")
    if args.status == "failed":
        if manifest["current_iteration"] < MAX_ITERATIONS:
            raise ContractError("failed는 최대 반복에 도달한 뒤에만 허용")
        if len(verifier_failures) < MAX_ITERATIONS or not all(verifier_failures[-MAX_ITERATIONS:]):
            raise ContractError("failed는 4회 연속 verifier 거부일 때만 허용")

    manifest["status"] = args.status
    manifest["updated_at"] = utc_now()
    manifest["finished_at"] = manifest["updated_at"]
    atomic_write(manifest_path(run_dir), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"run_id": manifest["run_id"], "status": args.status}, ensure_ascii=False))
    return 0


def command_status(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = validate_run(run_dir)
    summary = {
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "current_iteration": manifest["current_iteration"],
        "max_iterations": manifest["max_iterations"],
        "acceptance_score": manifest["acceptance_score"],
        "recorded_stages": manifest["stages"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="새 실행 디렉터리 생성")
    init_parser.add_argument("--root", default=".harness/runs")
    init_parser.add_argument("--run-id")
    init_parser.add_argument("--query-file")
    init_parser.set_defaults(func=command_init)

    record_parser = subparsers.add_parser("record", help="단계 산출물 검증 및 기록")
    record_parser.add_argument("--run-dir", required=True)
    record_parser.add_argument("--iteration", required=True, type=int)
    record_parser.add_argument("--stage", required=True, choices=sorted(ALL_STAGES))
    record_parser.add_argument("--input", required=True)
    record_parser.add_argument("--replace", action="store_true")
    record_parser.set_defaults(func=command_record)

    validate_parser = subparsers.add_parser("validate", help="전체 실행 상태 검증")
    validate_parser.add_argument("--run-dir", required=True)
    validate_parser.set_defaults(func=command_validate)

    finish_parser = subparsers.add_parser("finish", help="실행 종료 상태 기록")
    finish_parser.add_argument("--run-dir", required=True)
    finish_parser.add_argument("--status", required=True, choices=("accepted", "partial", "failed"))
    finish_parser.set_defaults(func=command_finish)

    status_parser = subparsers.add_parser("status", help="검증된 실행 요약 출력")
    status_parser.add_argument("--run-dir", required=True)
    status_parser.set_defaults(func=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ContractError, OSError) as exc:
        print(f"harness_state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

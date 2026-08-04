#!/usr/bin/env python3

import json
import pathlib
import sys


EXPECTED = ["law_researcher", "law_verifier", "persona_evaluator"]


def child_record(path: pathlib.Path):
    with path.open(encoding="utf-8") as handle:
        first = json.loads(handle.readline())
        source = first.get("payload", {}).get("source")
        if not isinstance(source, dict) or "subagent" not in source:
            return None
        spawn = source["subagent"].get("thread_spawn", {})
        role = spawn.get("agent_role")
        if role not in EXPECTED:
            return None
        parent = spawn.get("parent_thread_id")
        output = ""
        for line in handle:
            item = json.loads(line)
            payload = item.get("payload", {})
            if item.get("type") != "response_item" or payload.get("type") != "message":
                continue
            for content in payload.get("content", []):
                if content.get("type") == "output_text":
                    output += content.get("text", "")
    return path.stat().st_mtime_ns, role, parent, output


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_codex_agent_chain.py <start-marker>")

    marker_ns = pathlib.Path(sys.argv[1]).stat().st_mtime_ns
    session_root = pathlib.Path.home() / ".codex" / "sessions"
    by_parent = {}

    for path in session_root.rglob("*.jsonl"):
        if path.stat().st_mtime_ns < marker_ns:
            continue
        record = child_record(path)
        if record is None or record[2] is None:
            continue
        by_parent.setdefault(record[2], []).append(record)

    failures = []
    for parent, children in by_parent.items():
        children.sort()
        roles = [item[1] for item in children]
        if roles != EXPECTED:
            failures.append(f"{parent}: 실행 순서 {roles!r}")
            continue
        incomplete = [
            role
            for _, role, _, output in children
            if f'"agent_role":"{role}"' not in output or '"smoke_test":true' not in output
        ]
        if incomplete:
            failures.append(f"{parent}: 완료 표식 누락 {incomplete!r}")
            continue
        print(f"PASS  세 custom agent 실제 생성·순차 실행·완료 (parent={parent})")
        return

    detail = "; ".join(failures) if failures else "대상 자식 세션 없음"
    raise SystemExit(f"FAIL  custom agent 체인 미완료: {detail}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Count how many JSONL records have ALL tool calls succeeded.

Definition (configurable in code):
- A record is "all_success" if trajectory.tool_calls is a non-empty list AND
  each tool_call has a non-null result with no truthy `error/exception/traceback`.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any


def tool_call_ok(tc: Any) -> bool:
    if not isinstance(tc, dict):
        return False
    if "result" not in tc:
        return False
    r = tc.get("result")
    if r is None:
        return False

    if isinstance(r, dict):
        for k in ("error", "exception", "traceback"):
            v = r.get(k)
            if v:  # non-empty string / non-null object
                return False
        return True

    if isinstance(r, str):
        low = r.lower()
        if "traceback" in low or "exception" in low or "error" in low:
            return False
        return True

    # For other result types (list/number/bool), treat as ok as long as not None.
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", help="Path to the trajectory JSONL file")
    ap.add_argument("--top", type=int, default=20, help="Show top N failed tools (by failed calls)")
    args = ap.parse_args()

    counts = Counter()
    failed_tools = Counter()
    success_tools = Counter()

    with open(args.jsonl, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                counts["blank_lines"] += 1
                continue

            try:
                obj = json.loads(s)
            except Exception:
                counts["json_decode_error"] += 1
                continue

            counts["total_records"] += 1

            traj = obj.get("trajectory") or {}
            tool_calls = traj.get("tool_calls")

            if not tool_calls:
                counts["no_tool_calls"] += 1
                continue
            if not isinstance(tool_calls, list):
                counts["tool_calls_not_list"] += 1
                continue

            counts["records_with_tool_calls"] += 1

            fail_n = 0
            for tc in tool_calls:
                ok_call = tool_call_ok(tc)
                if ok_call:
                    counts["tool_calls_success"] += 1
                else:
                    counts["tool_calls_failed"] += 1
                    fail_n += 1
                    tool_name = None
                    if isinstance(tc, dict):
                        tool_name = tc.get("tool_name") or tc.get("name")
                    failed_tools[str(tool_name or "UNKNOWN")] += 1
                if ok_call:
                    tool_name = None
                    if isinstance(tc, dict):
                        tool_name = tc.get("tool_name") or tc.get("name")
                    success_tools[str(tool_name or "UNKNOWN")] += 1
                counts["total_tool_calls"] += 1

            if fail_n == 0:
                counts["all_tool_calls_success"] += 1
            else:
                counts["not_all_success"] += 1
            if fail_n <= 1:
                counts["at_most_one_failed_call"] += 1

    print("=== Summary ===")
    for k in (
        "total_records",
        "records_with_tool_calls",
        "all_tool_calls_success",
        "at_most_one_failed_call",
        "not_all_success",
        "no_tool_calls",
        "json_decode_error",
        "blank_lines",
        "total_tool_calls",
        "tool_calls_success",
        "tool_calls_failed",
    ):
        if k in counts:
            print(f"{k}: {counts[k]}")

    if failed_tools:
        print("\n=== Failed tool calls (top) ===")
        for name, n in failed_tools.most_common(args.top):
            print(f"{name}: {n}")

    if success_tools:
        print("\n=== Successful tool calls (top) ===")
        for name, n in success_tools.most_common(args.top):
            print(f"{name}: {n}")


if __name__ == "__main__":
    main()



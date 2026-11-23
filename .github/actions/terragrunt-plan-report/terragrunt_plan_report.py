#!/usr/bin/env python3
"""Turn Terraform plan JSON files into a markdown report that is safe to show in public.

The report lists each stack's resource changes by address and type only: no attribute
values, no plan output, no error text. Twelve-digit numbers (AWS account IDs) are
redacted as a backstop, in case one appears in a resource address.

Used for plans and applies. A stack's status is ok (planned, or applied), blocked (planned
but not applied, because it would destroy or replace something), failed, or skipped (not
run, because an earlier stack stopped the apply).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ACTION_ORDER = ("create", "update", "replace", "delete")
ACTION_LABELS = {"create": "Create", "update": "Update", "replace": "Replace", "delete": "Destroy"}
ACTION_EMOJI = {"create": "🟢", "update": "🟡", "replace": "🔵", "delete": "🔴"}
ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")


@dataclass(frozen=True)
class StackPlan:
    stack_path: str
    status: str  # "ok", "blocked", "failed" or "skipped"
    plan_json_path: Path | None


def redact(text: str) -> str:
    return ACCOUNT_ID.sub("************", text)


def normalize_actions(actions: list[str]) -> str | None:
    if actions in (["create"], ["update"], ["delete"]):
        return actions[0]
    if actions in (["delete", "create"], ["create", "delete"]):
        return "replace"
    return None  # no-op and read


def load_plan_index(path: Path) -> list[StackPlan]:
    """Each line: stack path, status, plan JSON path (empty when failed or skipped)."""
    stacks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        stack_path, status, plan_json = (line.split("\t") + ["", ""])[:3]
        stacks.append(StackPlan(stack_path, status, Path(plan_json) if plan_json else None))
    return stacks


def summarize_stack(stack: StackPlan) -> dict:
    if stack.status not in ("ok", "blocked") or stack.plan_json_path is None:
        status = "skipped" if stack.status == "skipped" else "failed"
        return {"stack_path": stack.stack_path, "status": status, "counts": {}, "resources": []}

    plan = json.loads(stack.plan_json_path.read_text(encoding="utf-8"))
    resources = []
    for change in plan.get("resource_changes") or []:
        action = normalize_actions((change.get("change") or {}).get("actions") or [])
        if action is not None:
            resources.append(
                {
                    "address": redact(change.get("address") or "(unknown)"),
                    "type": change.get("type") or "(unknown)",
                    "action": action,
                }
            )
    resources.sort(key=lambda r: (ACTION_ORDER.index(r["action"]), r["address"]))
    counts = Counter(r["action"] for r in resources)
    return {
        "stack_path": stack.stack_path,
        "status": stack.status,
        "counts": {action: counts.get(action, 0) for action in ACTION_ORDER},
        "resources": resources,
    }


def build_summary(title: str, stacks: list[StackPlan]) -> dict:
    summaries = [summarize_stack(stack) for stack in stacks]
    totals = Counter()
    for summary in summaries:
        totals.update(summary["counts"])
    return {
        "title": title,
        "totals": {action: totals.get(action, 0) for action in ACTION_ORDER},
        "failed": [s["stack_path"] for s in summaries if s["status"] == "failed"],
        "blocked": [s["stack_path"] for s in summaries if s["status"] == "blocked"],
        "stacks": summaries,
    }


def render_markdown(summary: dict) -> str:
    lines = [
        f"## {summary['title']}",
        "",
        "_Resource addresses and types only. Values and plan output are not shown; run the plan locally for details._",
        "",
        "| Action | Count |",
        "| --- | ---: |",
    ]
    for action in ACTION_ORDER:
        lines.append(f"| {ACTION_EMOJI[action]} {ACTION_LABELS[action]} | {summary['totals'][action]} |")
    if summary["failed"]:
        lines += ["", f"**❌ {len(summary['failed'])} stack(s) failed.** Error summaries are in the job log."]
    if summary["blocked"]:
        lines += [
            "",
            f"**⛔ {len(summary['blocked'])} stack(s) not applied:** they would destroy or replace resources. "
            "Apply those locally.",
        ]

    for stack in summary["stacks"]:
        path = stack["stack_path"]
        lines.append("")
        if stack["status"] == "failed":
            lines.append(f"- ❌ `{path}`: failed")
            continue
        if stack["status"] == "skipped":
            lines.append(f"- ⏭️ `{path}`: not run (an earlier stack stopped)")
            continue
        counts = stack["counts"]
        if not stack["resources"]:
            lines.append(f"- `{path}`: no changes")
            continue
        badges = " ".join(f"{ACTION_EMOJI[a]} {counts[a]}" for a in ACTION_ORDER if counts[a])
        mark = "⛔ " if stack["status"] == "blocked" else ""
        lines += [f"<details><summary>{mark}<code>{path}</code>: {badges}</summary>", ""]
        for resource in stack["resources"]:
            lines.append(f"- {ACTION_EMOJI[resource['action']]} `{resource['address']}` (`{resource['type']}`)")
        lines += ["", "</details>"]

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--plan-index-tsv", required=True)
    parser.add_argument("--out-markdown", required=True)
    args = parser.parse_args()

    stacks = load_plan_index(Path(args.plan_index_tsv))
    if not stacks:
        raise SystemExit("No Terragrunt stacks were planned")

    out = Path(args.out_markdown)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(build_summary(args.title, stacks)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

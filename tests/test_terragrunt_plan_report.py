from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


def load_plan_report_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "actions"
        / "terragrunt-plan-report"
        / "terragrunt_plan_report.py"
    )
    spec = importlib.util.spec_from_file_location("terragrunt_plan_report", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


terragrunt_plan_report = load_plan_report_module()


def write_plan(path: Path, changes: list[tuple[str, str, list[str]]], extra: dict | None = None) -> Path:
    path.write_text(
        json.dumps(
            {
                "resource_changes": [
                    {"address": address, "type": rtype, "change": {"actions": actions, **(extra or {})}}
                    for address, rtype, actions in changes
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


class TerragruntPlanReportTests(unittest.TestCase):
    def test_counts_changes_and_ignores_reads_and_no_ops(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            core = write_plan(
                temp / "core.json",
                [
                    ("aws_s3_bucket.ingest", "aws_s3_bucket", ["create"]),
                    ("aws_lambda_function.ingest", "aws_lambda_function", ["update"]),
                    ("data.aws_caller_identity.current", "aws_caller_identity", ["read"]),
                    ("aws_iam_role.unchanged", "aws_iam_role", ["no-op"]),
                ],
            )
            other = write_plan(
                temp / "other.json",
                [
                    ("aws_iam_role_policy.old", "aws_iam_role_policy", ["delete"]),
                    ("aws_lambda_function.emitter", "aws_lambda_function", ["create", "delete"]),
                ],
            )
            summary = terragrunt_plan_report.build_summary(
                "Plan",
                [
                    terragrunt_plan_report.StackPlan("live/dev/core", "ok", core),
                    terragrunt_plan_report.StackPlan("live/dev/other", "ok", other),
                ],
            )

        self.assertEqual(summary["totals"], {"create": 1, "update": 1, "replace": 1, "delete": 1})
        self.assertEqual(summary["failed"], [])
        self.assertEqual(len(summary["stacks"][0]["resources"]), 2)

    def test_report_shows_no_values_and_redacts_account_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = write_plan(
                Path(temp_dir) / "plan.json",
                [('aws_iam_role.this["arn:aws:iam::123456789012:root"]', "aws_iam_role", ["update"])],
                extra={"before": {"secret": "before-value"}, "after": {"secret": "after-value"}},
            )
            summary = terragrunt_plan_report.build_summary(
                "Plan", [terragrunt_plan_report.StackPlan("live/prod/role", "ok", plan)]
            )
        markdown = terragrunt_plan_report.render_markdown(summary)

        self.assertIn("aws_iam_role.this", markdown)
        self.assertNotIn("123456789012", markdown)
        self.assertNotIn("before-value", markdown)
        self.assertNotIn("after-value", markdown)

    def test_failed_stack_is_reported_without_details(self):
        summary = terragrunt_plan_report.build_summary(
            "Plan", [terragrunt_plan_report.StackPlan("live/prod/broken", "failed", None)]
        )
        markdown = terragrunt_plan_report.render_markdown(summary)

        self.assertEqual(summary["failed"], ["live/prod/broken"])
        self.assertIn("<summary>❌ <code>live/prod/broken</code>: failed</summary>", markdown)

    def test_blocked_and_skipped_stacks_in_an_apply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = write_plan(
                Path(temp_dir) / "plan.json",
                [("aws_s3_bucket.raw", "aws_s3_bucket", ["delete", "create"])],
            )
            summary = terragrunt_plan_report.build_summary(
                "Apply",
                [
                    terragrunt_plan_report.StackPlan("live/prod/raw-zone", "blocked", plan),
                    terragrunt_plan_report.StackPlan("live/prod/ingest", "skipped", None),
                ],
            )
        markdown = terragrunt_plan_report.render_markdown(summary)

        self.assertEqual(summary["blocked"], ["live/prod/raw-zone"])
        self.assertEqual(summary["failed"], [])
        self.assertEqual(summary["totals"]["replace"], 1)
        self.assertIn("1 stack(s) not applied", markdown)
        self.assertIn("⛔ <code>live/prod/raw-zone</code>", markdown)
        self.assertIn("<summary>⏭️ <code>live/prod/ingest</code>: not run</summary>", markdown)

    def test_every_stack_is_a_details_block(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            changed = write_plan(temp / "a.json", [("aws_s3_bucket.raw", "aws_s3_bucket", ["update"])])
            unchanged = write_plan(temp / "b.json", [("aws_s3_bucket.x", "aws_s3_bucket", ["no-op"])])
            summary = terragrunt_plan_report.build_summary(
                "Plan",
                [
                    terragrunt_plan_report.StackPlan("live/dev/ingest", "ok", changed),
                    terragrunt_plan_report.StackPlan("live/dev/raw-zone", "ok", unchanged),
                ],
            )
        markdown = terragrunt_plan_report.render_markdown(summary)

        self.assertEqual(markdown.count("<details>"), 2)
        self.assertIn("<summary><code>live/dev/raw-zone</code>: no changes</summary>", markdown)
        self.assertNotIn("\n- `live/", markdown)

    def test_load_plan_index_reads_status_and_optional_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index = Path(temp_dir) / "index.tsv"
            index.write_text("live/a\tok\t/tmp/a.json\nlive/b\tfailed\t\n", encoding="utf-8")
            stacks = terragrunt_plan_report.load_plan_index(index)

        self.assertEqual(stacks[0], terragrunt_plan_report.StackPlan("live/a", "ok", Path("/tmp/a.json")))
        self.assertEqual(stacks[1], terragrunt_plan_report.StackPlan("live/b", "failed", None))


if __name__ == "__main__":
    unittest.main()

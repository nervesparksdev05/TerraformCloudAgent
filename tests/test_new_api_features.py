import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.insights_service import (
    build_analytics_summary,
    build_dashboard_overview,
    build_resources_payload,
)
from app.services.settings_store import SettingsStore
from app.services.templates_catalog import compose_template_request


class NewApiFeaturesTests(unittest.TestCase):
    def test_dashboard_overview_zero_safe(self):
        data = build_dashboard_overview([], days=30)
        self.assertEqual(data["kpis"]["total_runs"], 0)
        self.assertEqual(data["kpis"]["active_runs"], 0)
        self.assertEqual(len(data["run_activity"]), 30)

    def test_resources_extracts_from_main_tf(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run_1"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "main.tf").write_text(
                """
resource "aws_vpc" "main" {
  tags = { env = "dev" }
}
resource "aws_subnet" "app" {}
""".strip(),
                encoding="utf-8",
            )
            runs = [
                {
                    "run_id": "run_1",
                    "status": "completed",
                    "provider": "aws",
                    "log_path": str(run_dir),
                    "created_at": "2026-02-01T00:00:00+00:00",
                    "updated_at": "2026-02-01T00:10:00+00:00",
                    "estimated_cost": 100,
                }
            ]
            payload = build_resources_payload(runs)
            self.assertEqual(payload["total"], 2)
            self.assertIn("aws_vpc", payload["available_types"])

    def test_analytics_summary_metrics(self):
        runs = [
            {
                "run_id": "r1",
                "status": "completed",
                "provider": "aws",
                "created_at": "2026-02-07T10:00:00+00:00",
                "duration": 20,
                "estimated_cost": 10,
            },
            {
                "run_id": "r2",
                "status": "failed",
                "provider": "gcp",
                "created_at": "2026-02-07T11:00:00+00:00",
                "duration": 0,
                "estimated_cost": 0,
            },
        ]
        summary = build_analytics_summary(runs, range_key="90d")
        self.assertEqual(summary["kpis"]["total_runs"], 2)
        self.assertEqual(summary["kpis"]["failed"], 1)
        self.assertGreaterEqual(summary["kpis"]["success_rate"], 0)

    def test_settings_get_put_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(file_path=Path(tmp) / "settings.json")
            initial = store.get()
            self.assertIn("notifications", initial)
            updated = store.update({"notifications": {"cost_alert": True}})
            self.assertTrue(updated["notifications"]["cost_alert"])

    def test_admin_delete_confirmation_required(self):
        client = TestClient(app)
        res = client.post("/admin/delete-all-runs", json={"confirmation": "WRONG"})
        self.assertEqual(res.status_code, 400)

        with patch("app.main.db.delete_all_runs", return_value={"runs_deleted": 1, "chat_messages_deleted": 2}), patch(
            "app.main._delete_all_run_workspaces", return_value=3
        ):
            ok = client.post("/admin/delete-all-runs", json={"confirmation": "DELETE ALL RUNS"})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["workspaces_deleted"], 3)

    def test_admin_reset_confirmation_required(self):
        client = TestClient(app)
        res = client.post("/admin/reset-application", json={"confirmation": "WRONG"})
        self.assertEqual(res.status_code, 400)

        with patch("app.main.db.delete_all_runs", return_value={"runs_deleted": 1, "chat_messages_deleted": 0}), patch(
            "app.main._delete_all_run_workspaces", return_value=1
        ), patch("app.main.settings_store.reset", return_value={"updated_at": "2026-02-08T00:00:00+00:00"}):
            ok = client.post("/admin/reset-application", json={"confirmation": "RESET APPLICATION"})
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.json()["ok"])

    def test_template_validation(self):
        request_text, template_name = compose_template_request(
            template_id="web_server",
            provider="aws",
            region="us-east-1",
            template_inputs={"size": "small"},
        )
        self.assertIn("Provider: AWS", request_text)
        self.assertEqual(template_name, "Web Server")

        with self.assertRaises(ValueError):
            compose_template_request(template_id="missing", provider="aws")


if __name__ == "__main__":
    unittest.main()

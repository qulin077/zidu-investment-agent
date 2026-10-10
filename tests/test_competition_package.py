from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompetitionPackageTests(unittest.TestCase):
    def test_public_fixture_is_explicitly_partial(self) -> None:
        data = json.loads((ROOT / "demo" / "dongshan_public_fixture.json").read_text(encoding="utf-8"))
        self.assertEqual(data["fixture_type"], "public_demo")
        dossier = data["summary"]["company_dossier"]
        self.assertEqual(dossier["research_completion"]["status"], "PARTIAL")
        self.assertEqual(len(data["summary"]["sources"]), 6)
        self.assertTrue(all(row["url"].startswith("https://") for row in data["summary"]["sources"]))

    def test_public_universe_contains_only_demo_company(self) -> None:
        import yaml

        # In the private working tree the public fixture stays under demo/ so
        # this test never inspects the owner's real watchlist.  The safe export
        # maps the same file to config/universe.yaml for the runtime.
        source = ROOT / "demo" / "universe.yaml"
        if not source.exists():
            source = ROOT / "config" / "universe.yaml"
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
        rows = data.get("stocks") or []
        self.assertEqual([(row["code"], row["name"]) for row in rows], [("002384", "东山精密")])

    def test_skills_are_runtime_loadable(self) -> None:
        from core.research import skills

        self.assertIn("Business Model", skills.require("company-research")["text"])
        self.assertEqual(len(skills.require("industry-research")["steps"]), 13)

    def test_anonymous_demo_initializes_and_smokes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            init = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "init_competition_demo.py"), "--db", str(db)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            payload = json.loads(init.stdout.strip())
            self.assertFalse(payload["private_data_imported"])
            smoke = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "competition_smoke.py"), "--db", str(db)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertEqual(json.loads(smoke.stdout)["private_rows"], 0)

    def test_personal_paths_and_secrets_are_not_in_demo_assets(self) -> None:
        # The private source tree intentionally contains the owner's journal.
        # A public export is identifiable by its top-level docs/ directory and
        # must never contain that directory as an actual path.
        if (ROOT / "docs").exists():
            self.assertFalse(any("10-我的交易" in path.parts for path in ROOT.rglob("*")))
        blob = "\n".join(
            path.read_text(encoding="utf-8")
            for base in (ROOT / "demo", ROOT / "docs")
            if base.exists()
            for path in base.rglob("*")
            if path.is_file()
        )
        mac_users_root = "/" + "Users" + "/"
        self.assertNotRegex(blob, re.escape(mac_users_root) + r"[^/\s]+")
        self.assertNotRegex(blob, r"sk-[A-Za-z0-9]{20,}")


if __name__ == "__main__":
    unittest.main()

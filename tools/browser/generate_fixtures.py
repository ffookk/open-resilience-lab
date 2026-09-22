"""Generate browser fixtures from the repository's fictional example only."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bundle_export import render_cards
from plan_studio import render_studio
from resilience_plan import render_plan, validate_plan


def generate():
    plan = json.loads((ROOT / "examples/fictional-household.json").read_text(encoding="utf-8"))
    plan["title"] = "Fictional browser plan\nSecond heading line"
    plan["contacts"][0]["name"] = "Fictional contact\nSecond name line"
    plan["meeting_points"][0]["instructions"] = "Fictional first line\nFictional second line\tTabbed detail"
    plan["notes"] = '<img src="https://example.invalid/blocked">\nFictional notes only'
    plan["sources"] = [{"title": "Fictional source", "url": "https://example.invalid/source",
                        "verified_on": "2026-09-20"}]
    validate_plan(plan)
    return {"fixture.json": json.dumps(plan), "studio.html": render_studio(),
            "plan.html": render_plan(plan), "cards.html": render_cards(plan, {})}


if __name__ == "__main__":
    print(json.dumps(generate()))

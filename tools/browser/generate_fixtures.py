"""Generate browser fixtures from the repository's fictional example only."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bundle_export import render_cards
from plan_studio import render_studio
from plan_review import compare_plans, render_review
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
    revised = copy.deepcopy(plan)
    revised["notes"] = '</pre><script>window.reviewInjected = true</script><img src="https://example.invalid/review-pixel">\nFictional revised notes'
    revised["household"].append({"name": "Fictional added member"})
    report = compare_plans(plan, revised)
    long_before = copy.deepcopy(plan)
    long_before["notes"] = "\n".join("BEFORE_LINE_%03d" % index for index in range(1, 241)) + "\n" + "W" * 120
    long_after = copy.deepcopy(long_before)
    long_after["notes"] = "\n".join("AFTER_LINE_%03d" % index for index in range(1, 241)) + "\n" + "M" * 120
    long_report = compare_plans(long_before, long_after)
    return {"long-review.html": render_review(long_report), "long-comparison.json": json.dumps(long_report),
            "review.html": render_review(report), "comparison.json": json.dumps(report), "fixture.json": json.dumps(plan), "studio.html": render_studio(),
            "plan.html": render_plan(plan), "cards.html": render_cards(plan, {})}


if __name__ == "__main__":
    print(json.dumps(generate()))

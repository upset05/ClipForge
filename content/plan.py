import json
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

def classify(text):
    t = text.lower()

    if any(x in t for x in ["gta 6", "gta vi", "grand theft auto", "vice city"]):
        return "GTA"

    if any(x in t for x in ["rockstar"]):
        return "Rockstar"

    if any(x in t for x in ["update", "patch", "release", "launch"]):
        return "Updates"

    return "Gaming"

def make_hook(title, category):
    if category == "GTA":
        return f"What this could mean for GTA fans: {title}"
    if category == "Rockstar":
        return f"Rockstar just gave us something to talk about: {title}"
    if category == "Updates":
        return f"Here's what changed: {title}"
    return f"This gaming story deserves attention: {title}"

def make_script(title, summary, category):
    summary = re.sub(r"\s+", " ", summary).strip()

    if len(summary) > 450:
        summary = summary[:447] + "..."

    return (
        f"HOOK: {make_hook(title, category)}\n\n"
        f"CONTEXT: {title}\n\n"
        f"DETAILS: {summary or 'Further research is required.'}\n\n"
        "ENDING: What do you think about this? Let us know."
    )

def main():
    files = sorted(
        REPORTS.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    files = [
        f for f in files
        if f.name != "content_plan.json"
    ]

    if not files:
        print("No discovery report found.")
        return

    with open(files[0], encoding="utf-8") as f:
        report = json.load(f)

    candidates = report.get("articles", [])
    selected = []
    used_categories = set()

    for article in candidates:
        category = classify(article["title"])

        if category not in used_categories:
            selected.append({
                "title": article["title"],
                "link": article["link"],
                "summary": article.get("summary", ""),
                "score": article.get("score", 0),
                "category": category,
                "hook": make_hook(article["title"], category),
                "script": make_script(
                    article["title"],
                    article.get("summary", ""),
                    category
                )
            })
            used_categories.add(category)

        if len(selected) >= 10:
            break

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ideas": selected
    }

    with open(REPORTS / "content_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    with open(REPORTS / f"ideas-{date}.md", "w", encoding="utf-8") as f:
        f.write(f"# ClipForge Content Plan — {date}\n\n")

        for i, idea in enumerate(selected, 1):
            f.write(f"## Idea {i}: {idea['category']}\n\n")
            f.write(f"**Title:** {idea['title']}\n\n")
            f.write(f"**Hook:** {idea['hook']}\n\n")
            f.write(f"**Source:** {idea['link']}\n\n")
            f.write(f"**Script draft:**\n\n{idea['script']}\n\n")
            f.write("---\n\n")

    print(f"Generated {len(selected)} content ideas.")

if __name__ == "__main__":
    main()

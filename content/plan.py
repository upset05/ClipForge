
import json
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

MAX_IDEAS = 10


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def classify(text):
    t = text.lower()

    if any(x in t for x in [
        "gta 6", "gta vi", "grand theft auto", "vice city"
    ]):
        return "GTA"

    if "rockstar" in t:
        return "Rockstar"

    if any(x in t for x in [
        "update", "patch", "release", "launch"
    ]):
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
    summary = clean(summary)

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

    with open(files[0], encoding="utf-8") as file:
        report = json.load(file)

    candidates = report.get("articles", [])

    selected = []
    seen_links = set()

    for article in candidates:
        title = clean(article.get("title"))
        link = article.get("link", "")

        if not title or not link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)

        category = classify(title)
        summary = clean(article.get("summary", ""))

        idea = {
            "title": title,
            "link": link,
            "summary": summary,
            "score": article.get("score", 0),
            "category": category,

            "image_url": article.get("image_url", ""),
            "image_caption": article.get("image_caption", ""),
            "image_source": article.get("image_source", "unavailable"),

            "published": article.get("published", ""),
            "source": article.get("source", ""),

            "hook": make_hook(title, category),
            "script": make_script(title, summary, category)
        }

        selected.append(idea)

        if len(selected) >= MAX_IDEAS:
            break

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    plan = {
        "generated_at": now.isoformat(),
        "source_report": files[0].name,
        "total_ideas": len(selected),
        "ideas": selected
    }

    plan_path = REPORTS / "content_plan.json"

    with open(plan_path, "w", encoding="utf-8") as file:
        json.dump(
            plan,
            file,
            indent=2,
            ensure_ascii=False
        )

    markdown_path = REPORTS / f"ideas-{date}.md"

    with open(markdown_path, "w", encoding="utf-8") as file:
        file.write(f"# ClipForge Content Plan — {date}\n\n")
        file.write(f"Generated ideas: {len(selected)}\n\n")

        for i, idea in enumerate(selected, 1):
            file.write(f"## Idea {i}: {idea['category']}\n\n")
            file.write(f"**Title:** {idea['title']}\n\n")
            file.write(f"**Hook:** {idea['hook']}\n\n")
            file.write(f"**Image:** {idea['image_url'] or 'Not available'}\n\n")
            file.write(f"**Source:** {idea['link']}\n\n")
            file.write(f"**Script draft:**\n\n{idea['script']}\n\n")
            file.write("---\n\n")

    with_images = sum(
        1 for idea in selected if idea["image_url"]
    )

    print("--------------------------------")
    print(f"Generated ideas: {len(selected)}")
    print(f"Ideas with images: {with_images}")
    print(f"Plan: {plan_path}")
    print("Content planning complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()

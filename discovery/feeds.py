import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "discovery" / "sources.json"
OUTPUT = ROOT / "reports"

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def score_article(article, keywords, priority):
    text = clean(
        f"{article.get('title', '')} "
        f"{article.get('summary', '')}"
    ).lower()

    score = 0

    for word in keywords:
        if word.lower() in text:
            score += 1

    for word in priority:
        if word.lower() in text:
            score += 5

    return score

def main():
    with open(CONFIG, encoding="utf-8") as f:
        config = json.load(f)

    OUTPUT.mkdir(exist_ok=True)

    articles = []
    seen = set()

    for url in config["feeds"]:
        try:
            feed = feedparser.parse(url)

            if getattr(feed, "bozo", False):
                print(f"Feed warning: {url}")

            for entry in feed.entries:
                title = clean(entry.get("title"))
                link = entry.get("link", "")

                if not title or not link:
                    continue

                key = hashlib.sha256(
                    link.encode("utf-8")
                ).hexdigest()

                if key in seen:
                    continue

                seen.add(key)

                score = score_article(
                    entry,
                    config["keywords"],
                    config["priority_keywords"]
                )

                if score <= 0:
                    continue

                articles.append({
                    "title": title,
                    "link": link,
                    "summary": clean(entry.get("summary")),
                    "score": score,
                    "source": url
                })

        except Exception as e:
            print(f"Feed failed: {url} | {e}")

    articles.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    report = {
        "generated_at": now.isoformat(),
        "total_candidates": len(articles),
        "articles": articles[:50]
    }

    json_path = OUTPUT / f"{date}.json"
    md_path = OUTPUT / f"{date}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# ClipForge Discovery — {date}\n\n")
        f.write(f"Found {len(articles)} relevant articles.\n\n")

        for article in articles[:30]:
            f.write(f"## {article['title']}\n\n")
            f.write(f"Score: {article['score']}\n\n")
            f.write(f"{article['summary'][:600]}\n\n")
            f.write(f"Source: {article['link']}\n\n")
            f.write("---\n\n")

    print(f"Candidates: {len(articles)}")
    print(f"Report: {md_path}")

if __name__ == "__main__":
    main()

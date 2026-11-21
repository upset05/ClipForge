
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "discovery" / "sources.json"
OUTPUT = ROOT / "reports"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v")

HEADERS = {
    "User-Agent": "ClipForge/1.0 (gaming news discovery)"
}


def clean(value):
    value = html.unescape(str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def valid_media_url(url, base_url=""):
    url = html.unescape(str(url or "")).strip()

    if not url:
        return ""

    url = urljoin(base_url, url)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    return url


def media_kind(url, media_type=""):
    media_type = str(media_type or "").lower()
    path = urlparse(url).path.lower()

    if media_type.startswith("video/") or path.endswith(VIDEO_EXTENSIONS):
        return "video"

    if media_type.startswith("image/") or path.endswith(IMAGE_EXTENSIONS):
        return "image"

    return ""


class MediaHTMLParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "img":
            url = attrs.get("src") or attrs.get("data-src") or attrs.get("data-original")
            self.add(url, "image", attrs.get("alt", ""), "embedded_html")

        elif tag == "video":
            self.add(
                attrs.get("src"),
                "video",
                attrs.get("title", ""),
                "embedded_html"
            )
            self.add(
                attrs.get("poster"),
                "image",
                attrs.get("title", ""),
                "video_poster"
            )

        elif tag == "source":
            url = attrs.get("src")
            kind = media_kind(url or "", attrs.get("type", ""))

            if kind:
                self.add(url, kind, "", "embedded_html")

        elif tag == "a":
            url = attrs.get("href", "")
            kind = media_kind(url)

            if kind == "video":
                self.add(url, "video", "", "linked_video")

    def add(self, url, kind, caption, discovered_from):
        url = valid_media_url(url, self.base_url)

        if not url:
            return

        self.assets.append({
            "url": url,
            "kind": kind,
            "caption": clean(caption),
            "discovered_from": discovered_from
        })


def creator_from_entry(entry):
    author = clean(entry.get("author", ""))

    if author:
        return author

    authors = entry.get("authors", [])

    if authors:
        return clean(authors[0].get("name", ""))

    return ""


def extract_media(entry, article_url, publisher):
    assets = []
    seen = set()

    def add_asset(url, kind="", caption="", creator="", discovered_from="rss"):
        url = valid_media_url(url, article_url)

        if not url:
            return

        kind = kind or media_kind(url)

        if kind not in ("image", "video"):
            return

        if url in seen:
            return

        seen.add(url)

        assets.append({
            "url": url,
            "kind": kind,
            "caption": clean(caption),
            "creator": clean(creator),
            "publisher": publisher,
            "source_url": article_url,
            "discovered_from": discovered_from,
            "license": "",
            "rights_status": "unverified",
            "approved_for_reuse": False
        })

    entry_creator = creator_from_entry(entry)

    # Media RSS content
    for media in entry.get("media_content", []):
        add_asset(
            media.get("url", ""),
            media_kind(
                media.get("url", ""),
                media.get("type", "")
            ),
            media.get("title", ""),
            media.get("credit", "") or entry_creator,
            "media_content"
        )

    # Media RSS thumbnails
    for media in entry.get("media_thumbnail", []):
        add_asset(
            media.get("url", ""),
            "image",
            media.get("title", ""),
            entry_creator,
            "media_thumbnail"
        )

    # Enclosures
    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("href") or enclosure.get("url", "")
        kind = media_kind(url, enclosure.get("type", ""))

        if kind:
            add_asset(
                url,
                kind,
                enclosure.get("title", ""),
                entry_creator,
                "enclosure"
            )

    # Other RSS links
    for link in entry.get("links", []):
        url = link.get("href", "")
        kind = media_kind(url, link.get("type", ""))

        if kind:
            add_asset(
                url,
                kind,
                link.get("title", ""),
                entry_creator,
                "rss_link"
            )

    # Images and videos embedded in summaries or content
    html_blocks = [entry.get("summary", "")]

    for content in entry.get("content", []):
        html_blocks.append(content.get("value", ""))

    for block in html_blocks:
        parser = MediaHTMLParser(article_url)

        try:
            parser.feed(str(block or ""))
        except Exception:
            continue

        for asset in parser.assets:
            add_asset(
                asset["url"],
                asset["kind"],
                asset["caption"],
                entry_creator,
                asset["discovered_from"]
            )

    return assets


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


def publisher_name(feed, feed_url):
    name = clean(feed.feed.get("title", ""))

    if name:
        return name

    return urlparse(feed_url).netloc.replace("www.", "")


def main():
    with open(CONFIG, encoding="utf-8") as file:
        config = json.load(file)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    articles = []
    seen = set()

    max_articles = config.get("limits", {}).get("max_articles", 50)
    max_images = config.get("limits", {}).get("max_images_per_article", 8)
    max_videos = config.get("limits", {}).get("max_videos_per_article", 5)

    print("ClipForge discovery starting...")

    for feed_url in config.get("feeds", []):
        try:
            print(f"Checking feed: {feed_url}")

            feed = feedparser.parse(feed_url)

            if getattr(feed, "bozo", False):
                print(f"Feed warning: {feed_url}")

            publisher = publisher_name(feed, feed_url)

            for entry in feed.entries:
                title = clean(entry.get("title"))
                link = valid_media_url(entry.get("link", ""))

                if not title or not link:
                    continue

                article_id = hashlib.sha256(
                    link.encode("utf-8")
                ).hexdigest()

                if article_id in seen:
                    continue

                score = score_article(
                    entry,
                    config.get("keywords", []),
                    config.get("priority_keywords", [])
                )

                if score <= 0:
                    continue

                seen.add(article_id)

                media = extract_media(entry, link, publisher)

                images = [
                    item for item in media
                    if item["kind"] == "image"
                ][:max_images]

                videos = [
                    item for item in media
                    if item["kind"] == "video"
                ][:max_videos]

                selected_media = images + videos

                published = (
                    entry.get("published")
                    or entry.get("updated")
                    or ""
                )

                article = {
                    "id": article_id[:16],
                    "title": title,
                    "link": link,
                    "summary": clean(entry.get("summary", "")),
                    "score": score,
                    "source": publisher,
                    "feed_url": feed_url,
                    "published": published,
                    "author": creator_from_entry(entry),
                    "media_assets": selected_media,
                    "image_urls": [item["url"] for item in images],
                    "video_urls": [item["url"] for item in videos],
                    "image_url": images[0]["url"] if images else "",
                    "image_caption": images[0]["caption"] if images else "",
                    "image_source": publisher if images else "unavailable",
                    "media_rights_review_required": bool(selected_media)
                }

                articles.append(article)

        except Exception as error:
            print(f"Feed failed: {feed_url} | {error}")

    articles.sort(
        key=lambda item: (
            item["score"],
            item["published"]
        ),
        reverse=True
    )

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")

    selected = articles[:max_articles]

    report = {
        "generated_at": now.isoformat(),
        "total_candidates": len(articles),
        "articles_with_images": sum(
            1 for article in selected if article["image_urls"]
        ),
        "articles_with_videos": sum(
            1 for article in selected if article["video_urls"]
        ),
        "total_media_candidates": sum(
            len(article["media_assets"]) for article in selected
        ),
        "articles": selected
    }

    json_path = OUTPUT / f"{date}.json"
    md_path = OUTPUT / f"{date}.md"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as file:
        file.write(f"# ClipForge Discovery — {date}\n\n")
        file.write(f"Relevant articles: {len(selected)}\n\n")
        file.write(f"Articles with images: {report['articles_with_images']}\n\n")
        file.write(f"Articles with videos: {report['articles_with_videos']}\n\n")
        file.write(f"Media candidates: {report['total_media_candidates']}\n\n")

        for article in selected:
            file.write(f"## {article['title']}\n\n")
            file.write(f"**Score:** {article['score']}\n\n")
            file.write(f"**Publisher:** {article['source']}\n\n")
            file.write(f"{article['summary'][:700]}\n\n")
            file.write(f"**Article:** {article['link']}\n\n")

            for asset in article["media_assets"]:
                file.write(
                    f"- {asset['kind'].title()}: {asset['url']}\n"
                )
                file.write(
                    f"  - Creator: {asset['creator'] or 'Not identified'}\n"
                )
                file.write(
                    f"  - Rights: {asset['rights_status']}\n"
                )
                file.write(
                    f"  - Reuse approved: No\n"
                )

            if not article["media_assets"]:
                file.write("No media candidates found in the feed.\n")

            file.write("\n---\n\n")

    print("--------------------------------")
    print(f"Candidates discovered: {len(articles)}")
    print(f"Articles selected: {len(selected)}")
    print(f"Articles with images: {report['articles_with_images']}")
    print(f"Articles with videos: {report['articles_with_videos']}")
    print(f"Media candidates: {report['total_media_candidates']}")
    print(f"Report: {json_path}")
    print("Discovery complete.")
    print("--------------------------------")


if __name__ == "__main__":
    main()


import json
import re
import time
import html
import os
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime


MODEL = "gemini-3.8-flash"
BATCH_SIZE = 5
MAX_RETRIES = 4

FEEDS = [
    ("Markets", "Business Standard Markets",
     "https://www.business-standard.com/rss/markets-106.rss"),
    ("Companies", "Business Standard Companies",
     "https://www.business-standard.com/rss/companies-101.rss"),
    ("Economy", "Business Standard Finance",
     "https://www.business-standard.com/rss/finance-103.rss"),
    ("NSE", "NSE India",
     "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"),
    ("Markets", "Google News India Markets",
     "https://news.google.com/rss/search?q=Indian+stock+market+Nifty+Sensex&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Economy", "Google News India Economy",
     "https://news.google.com/rss/search?q=India+economy+RBI+SEBI&hl=en-IN&gl=IN&ceid=IN:en"),
]

OUTPUT_FILE = Path("data/news.json")


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_feed(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 OneDayShaikNews/1.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return ET.fromstring(response.read())


def parse_date(value):
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def load_old_news():
    try:
        if OUTPUT_FILE.exists():
            data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            return data.get("items", [])
    except Exception as error:
        print("Old news read warning:", error)

    return []


def previous_translations(old_items):
    saved = {}

    for item in old_items:
        key = item.get("link") or item.get("title", "").lower()

        if key and item.get("hinglish_title") and item.get("explanation"):
            saved[key] = {
                "hinglish_title": item["hinglish_title"],
                "explanation": item["explanation"]
            }

    return saved


def call_gemini(headlines, api_key):
    prompt = """
You write news for an Indian stock-market website.

Convert every headline into natural, simple Roman Hindi/Hinglish.
Use ENGLISH LETTERS ONLY. Never use Devanagari.

Return ONLY a valid JSON array. Each object must contain:
{
  "hinglish_title": "Short Roman Hinglish headline",
  "explanation": "One or two short sentences in simple Roman Hinglish"
}

Rules:
- Explain only what the supplied headline says.
- Do not invent facts, figures, reasons or market impact.
- Do not make stock predictions or give trading advice.
- Keep company names and numbers unchanged.
- If details are unclear, say: "Puri details original report mein check karein."

Headlines:
""" + json.dumps(headlines, ensure_ascii=False)

    payload = json.dumps({
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }).encode("utf-8")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + MODEL + ":generateContent?key=" + api_key
    )

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates: " +
                         json.dumps(data)[:1000])

    parts = candidates[0].get("content", {}).get("parts", [])
    response_text = "".join(
        part.get("text", "") for part in parts
    ).strip()

    # Remove optional Markdown code fences
    response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
    response_text = re.sub(r"\s*```$", "", response_text)

    result = json.loads(response_text)

    if not isinstance(result, list) or len(result) != len(headlines):
        raise ValueError("Gemini returned an unexpected number of translations")

    for item in result:
        if not isinstance(item, dict):
            raise ValueError("Invalid translation object")

        if not clean(item.get("hinglish_title")):
            raise ValueError("Missing Hinglish headline")

        if not clean(item.get("explanation")):
            raise ValueError("Missing explanation")

    return result


def translate_batch(headlines, api_key):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"Gemini batch: {len(headlines)} headlines "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )
            return call_gemini(headlines, api_key)

        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            print(f"Gemini HTTP {error.code}: {details[:800]}")

            if error.code not in (429, 500, 502, 503, 504):
                break

        except Exception as error:
            print("Gemini request error:", str(error)[:800])

        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(f"Retrying after {wait} seconds...")
            time.sleep(wait)

    return None


def main():
    print("One Day Shaik news updater started.")

    old_items = load_old_news()
    old_translations = previous_translations(old_items)

    items = []
    seen = set()

    # Collect news from RSS feeds
    for category, source, url in FEEDS:
        try:
            root = fetch_feed(url)

            for node in root.findall(".//item"):
                title = clean(node.findtext("title"))
                link = clean(node.findtext("link"))
                published = clean(node.findtext("pubDate"))

                if not title or not link:
                    continue

                unique_key = link.lower()

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                items.append({
                    "category": category,
                    "source": source,
                    "title": title,
                    "link": link,
                    "published": parse_date(published),
                    "hinglish_title": "",
                    "explanation": ""
                })

            print("Feed checked:", source)

        except Exception as error:
            print(f"Feed failed: {source}: {error}")

    items.sort(
        key=lambda item: item.get("published", ""),
        reverse=True
    )
    items = items[:40]

    print("Total headlines collected:", len(items))

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    translated_count = 0
    failed_count = 0

    if api_key and items:
        for start in range(0, len(items), BATCH_SIZE):
            batch = items[start:start + BATCH_SIZE]
            headlines = [item["title"] for item in batch]

            translations = translate_batch(headlines, api_key)

            if translations:
                for item, translation in zip(batch, translations):
                    item["hinglish_title"] = clean(
                        translation.get("hinglish_title")
                    )
                    item["explanation"] = clean(
                        translation.get("explanation")
                    )
                    translated_count += 1
            else:
                failed_count += len(batch)

                # Preserve an earlier successful translation
                for item in batch:
                    key = item["link"]
                    old = old_translations.get(key)

                    if old:
                        item.update(old)
                        translated_count += 1

        print("Translated headlines:", translated_count)
        print("Untranslated headlines:", failed_count)

    else:
        print("ERROR: GEMINI_API_KEY is missing or no headlines found.")

        for item in items:
            old = old_translations.get(item["link"])
            if old:
                item.update(old)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": items
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("Saved headlines:", len(items))
    print("News JSON updated successfully.")


if __name__ == "__main__":
    main()

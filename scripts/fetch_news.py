import json
import os
import re
import time
import hashlib
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

MODEL = "gemini-3.8-flash"
API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + MODEL + ":generateContent?key="
)

NEWS_FILE = Path("data/news.json")
CACHE_FILE = Path("data/translations.json")
STATE_FILE = Path("data/translation_state.json")

MAX_HEADLINES = 40
TRANSLATION_COOLDOWN_HOURS = 4

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


def now_utc():
    return datetime.now(timezone.utc)


def iso_now():
    return now_utc().isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def clean(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def fetch_feed(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 OneDayShaikNews/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return ET.fromstring(response.read())


def parse_date(value):
    try:
        result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def get_items():
    items = []
    seen = set()

    for category, source, url in FEEDS:
        try:
            root = fetch_feed(url)
            for node in root.findall(".//item"):
                title = clean(node.findtext("title"))
                link = clean(node.findtext("link"))
                published = clean(node.findtext("pubDate"))

                # RSS descriptions are short publisher-provided feed summaries.
                description = clean(node.findtext("description"))
                if not description:
                    description = ""

                if not title or not link:
                    continue

                identity = link.lower() or title.lower()
                if identity in seen:
                    continue
                seen.add(identity)

                items.append({
                    "category": category,
                    "source": source,
                    "title": title,
                    "link": link,
                    "published": parse_date(published),
                    "rss_summary": description[:1800],
                    "hinglish_title": "",
                    "explanation": ""
                })

            print("Feed checked:", source)
        except Exception as error:
            print("Feed failed:", source, error)

    items.sort(
        key=lambda item: item.get("published") or "",
        reverse=True
    )
    return items[:MAX_HEADLINES]


def title_key(title):
    return hashlib.sha256(
        title.strip().lower().encode("utf-8")
    ).hexdigest()


def retry_time_from_error(message):
    match = re.search(
        r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?",
        message,
        re.IGNORECASE
    )
    if not match:
        return now_utc() + timedelta(hours=6)

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    delay = max(hours * 3600 + minutes * 60 + seconds, 3600)
    return now_utc() + timedelta(seconds=delay + 60)


def translate_headlines(headlines, api_key):
    prompt = """
You write for an Indian news website called One Day Shaik.

For every supplied news item, produce:
1) A short, natural Roman Hinglish headline.
2) A simple 3 to 5 line Roman Hinglish summary based ONLY on the supplied headline
   and RSS summary text.

Language rules:
- Use English letters only. Never use Devanagari script.
- Use everyday Roman Hindi/Hinglish that an Indian reader can understand.
- Keep company names, stock names, people names, dates and numbers accurate.
- Explain the available facts clearly; do not merely repeat the headline.
- If the RSS summary has too little information, explain only what is known
  and say: "Zyada details ke liye original report dekhein."
- Never invent facts, quotes, figures, reasons, market predictions or buy/sell advice.
- Do not translate names of companies or people.
- Return ONLY a valid JSON array, with exactly one result per input ID.
- Each explanation should be 3 to 5 short sentences when enough source detail exists.
- If source detail is limited, a shorter honest explanation is better than guessing.

Required JSON shape:
[
  {
    "id": 1,
    "hinglish_title": "Roman Hinglish headline",
    "explanation": "Roman Hinglish summary..."
  }
]

News items:
""" + json.dumps(headlines, ensure_ascii=False)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    request = urllib.request.Request(
        API_URL + api_key,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())

    response_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
        response_text = re.sub(r"\s*```$", "", response_text)

    result = json.loads(response_text)
    if not isinstance(result, list):
        raise ValueError("Gemini response was not a JSON list")

    translated = {}
    for entry in result:
        try:
            item_id = int(entry["id"])
            if not 1 <= item_id <= len(headlines):
                continue
            title = clean(entry.get("hinglish_title"))
            explanation = clean(entry.get("explanation"))
            if title and explanation:
                translated[item_id] = {
                    "hinglish_title": title,
                    "explanation": explanation
                }
        except (KeyError, TypeError, ValueError):
            continue
    return translated


def main():
    print("One Day Shaik news updater started.")
    items = get_items()
    print("Total headlines collected:", len(items))

    cache = read_json(CACHE_FILE, {})
    state = read_json(STATE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    if not isinstance(state, dict):
        state = {}

    # Reuse saved translations first. This avoids spending API quota again.
    for item in items:
        saved = cache.get(title_key(item["title"]))
        if saved:
            item["hinglish_title"] = saved.get("hinglish_title", "")
            item["explanation"] = saved.get("explanation", "")

    missing = [
        item for item in items
        if not item["hinglish_title"] or not item["explanation"]
    ]
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        print("GEMINI_API_KEY missing.")
    elif not missing:
        print("All current headlines already have saved translations.")
    else:
        next_attempt = state.get("next_attempt_at", "")
        try:
            allowed_time = datetime.fromisoformat(
                next_attempt.replace("Z", "+00:00")
            ) if next_attempt else None
        except ValueError:
            allowed_time = None

        if allowed_time and now_utc() < allowed_time:
            print("Translation cooldown active until:", next_attempt)
        else:
            request_items = [
                {
                    "id": index + 1,
                    "title": item["title"],
                    "rss_summary": item.get("rss_summary", "")
                }
                for index, item in enumerate(missing)
            ]
            print("Sending one Gemini request for", len(missing), "headlines.")

            try:
                translated = translate_headlines(request_items, api_key)
                for index, item in enumerate(missing, start=1):
                    result = translated.get(index)
                    if result:
                        cache[title_key(item["title"])] = result
                        item["hinglish_title"] = result["hinglish_title"]
                        item["explanation"] = result["explanation"]

                state["last_success_at"] = iso_now()
                # Avoid repeated API calls on every 15-minute workflow run.
                state["next_attempt_at"] = (
                    now_utc() + timedelta(hours=TRANSLATION_COOLDOWN_HOURS)
                ).isoformat()
                print("Translations saved:", len(translated))

            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                print("Gemini HTTP error:", error.code, body[:2500])
                if error.code == 429:
                    retry_at = retry_time_from_error(body)
                    state["next_attempt_at"] = retry_at.isoformat()
                    print("Quota limit reached. Retry after:", retry_at)
                else:
                    state["next_attempt_at"] = (
                        now_utc() + timedelta(hours=1)
                    ).isoformat()
            except Exception as error:
                print("Translation error:", error)
                state["next_attempt_at"] = (
                    now_utc() + timedelta(hours=1)
                ).isoformat()

    # Apply cache one more time and preserve the website's existing JSON fields.
    for item in items:
        saved = cache.get(title_key(item["title"]))
        if saved:
            item["hinglish_title"] = saved.get("hinglish_title", "")
            item["explanation"] = saved.get("explanation", "")

    write_json(CACHE_FILE, cache)
    write_json(STATE_FILE, state)

    output = {"updated": iso_now(), "items": items}
    write_json(NEWS_FILE, output)

    translated_count = sum(
        1 for item in items
        if item["hinglish_title"] and item["explanation"]
    )
    print("Saved headlines:", len(items))
    print("Headlines with Hinglish translation:", translated_count)
    print("News update completed.")


if __name__ == "__main__":
    main()

import json, re, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
import os

FEEDS = [
    ("Markets", "Business Standard Markets", "https://www.business-standard.com/rss/markets-106.rss"),
    ("Companies", "Business Standard Companies", "https://www.business-standard.com/rss/companies-101.rss"),
    ("Economy", "Business Standard Finance", "https://www.business-standard.com/rss/finance-103.rss"),
    ("NSE", "NSE India", "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"),
    ("Markets", "Google News India Markets", "https://news.google.com/rss/search?q=Indian+stock+market+Nifty+Sensex&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Economy", "Google News India Economy", "https://news.google.com/rss/search?q=India+economy+RBI+SEBI&hl=en-IN&gl=IN&ceid=IN:en"),
]
def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 OneDayShaikNews/1.0"})
    with urllib.request.urlopen(req,timeout=20) as r:return ET.fromstring(r.read())
def parse_date(s):
    try:
        d=parsedate_to_datetime(s)
        if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:return ""
def explain_with_gemini(headlines, api_key):
    prompt = """You write a simple Indian stock-market news website in natural Roman Hindi/Hinglish, using ENGLISH LETTERS ONLY (never Devanagari).
For each supplied headline, return JSON array with objects: {"hinglish_title":"short natural Roman Hinglish headline","explanation":"1-2 short sentences in simple Roman Hinglish explaining only what the headline says."}
Rules: Do not invent facts, numbers, causes, market impact, predictions, or advice. If headline is unclear, say that details original report mein check karein. Do not claim a stock will rise/fall. Keep company names and figures unchanged. Output only valid JSON array.
Headlines:\n""" + json.dumps(headlines, ensure_ascii=False)
    payload=json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"responseMimeType":"application/json"}}).encode()
    url="https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key="+api_key
    req=urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=45) as r: data=json.loads(r.read())
    text=data["candidates"][0]["content"]["parts"][0]["text"]
    result=json.loads(text)
    if not isinstance(result,list) or len(result)!=len(headlines):raise ValueError("Unexpected AI response")
    return result
def main():
    items=[];seen=set()
    for category,source,url in FEEDS:
        try:
            root=fetch(url)
            for node in root.findall(".//item"):
                title=clean(node.findtext("title"));link=clean(node.findtext("link"));pub=clean(node.findtext("pubDate"))
                if not title or not link or title.lower() in seen:continue
                seen.add(title.lower())
                items.append({"category":category,"source":source,"title":title,"link":link,"published":parse_date(pub)})
        except Exception as e:print(f"Feed failed: {source}: {e}")
    items.sort(key=lambda x:x["published"],reverse=True)
    items=items[:40]
    key=os.environ.get("GEMINI_API_KEY","").strip()
    if key and items:
        try:
            translated=explain_with_gemini([x["title"] for x in items],key)
            for item,extra in zip(items,translated):
                item["hinglish_title"]=clean(extra.get("hinglish_title"))
                item["explanation"]=clean(extra.get("explanation"))
            print("Roman Hinglish explanations generated.")
        except Exception as e:
            print("AI translation unavailable; original headlines will be shown:",e)
    else:print("GEMINI_API_KEY not set; original headlines will be shown until free API key is configured.")
    out=Path("data/news.json");out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"updated":datetime.now(timezone.utc).isoformat(),"items":items},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Saved {len(items)} headlines")
if __name__=="__main__":main()

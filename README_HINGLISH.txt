ONE DAY SHAIK — FREE PUBLIC MARKET NEWS WEBSITE

Website language:
- Roman Hindi / Hinglish using English letters only.
- Each headline can have a short, simple explanation.
- The explanation must only restate what the headline says; it must not invent market impact or trading advice.

AUTO NEWS:
- RSS feeds: NSE announcements, Business Standard, Google News India.
- GitHub Actions attempts an update every 15 minutes. GitHub may delay scheduled runs.
- Website refreshes the news data every 5 minutes while open.

OPTIONAL FREE AI HINGLISH:
To generate Roman-Hinglish headlines and explanations:
1. Create an API key in Google AI Studio: https://aistudio.google.com/app/apikey
2. In GitHub repository open Settings > Secrets and variables > Actions > New repository secret.
3. Name: GEMINI_API_KEY
4. Value: paste your API key.
5. Save, then open Actions > Update market headlines > Run workflow.

The AI free tier, model availability and rate limits can change. This website works without the key, but then original publisher headlines appear without AI explanations. Never put the key in website files or commit it to GitHub.

PUBLISH:
1. Create a PUBLIC GitHub repository named one-day-shaik.
2. Upload all files and folders from this ZIP, including the hidden .github folder.
3. Settings > Pages > Deploy from a branch > main > /(root) > Save.
4. Actions tab > Update market headlines > Run workflow.
5. Actions > General > Workflow permissions > Read and write permissions, if workflow cannot push data/news.json.
6. Site URL: https://YOUR-GITHUB-USERNAME.github.io/one-day-shaik/

NOTES:
- GitHub Pages is static hosting; no private broker credentials are needed.
- RSS feeds can be delayed or unavailable.
- News is for information only, not investment advice.
- Verify details in the original linked article.

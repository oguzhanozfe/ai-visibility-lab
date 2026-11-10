"""Paste a link, get the score: a one-page local web app (standard library only).

    python3 -m geo.web            # then open http://127.0.0.1:8765
"""
import html
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from geo.audit import audit, score

FIX = {
    "AI answer bots allowed in robots.txt": "Allow answer and search bots (OAI-SearchBot, PerplexityBot, ChatGPT-User, Claude-User); you can still block training bots.",
    "AI training bots (info, not scored)": "",
    "llms.txt present": "Add /llms.txt: a short Markdown index of your most useful pages.",
    "Structured data (JSON-LD)": "Add JSON-LD Article or NewsArticle markup.",
    "Schema has headline, date and author": "Fill headline, datePublished and author in the JSON-LD.",
    "Publish date in the page": "Show the date in a <time datetime> tag or an article:published_time meta tag.",
    "One H1": "Use exactly one H1 for the page title.",
    "Answer in the first paragraph": "Answer the headline's question in the first 60 words.",
    "Question-style subheading": "Add a subheading phrased as the reader's question.",
    "Text present in the HTML": "Serve the article text in the HTML, not only through JavaScript.",
    "Canonical link": "Add <link rel=\"canonical\">.",
}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI visibility check</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;color:#1d1d1f;background:#fafafa}}
input{{width:100%;padding:.6rem;font-size:1rem;box-sizing:border-box}} button{{margin-top:.5rem;padding:.5rem 1rem;font-size:1rem}}
table{{border-collapse:collapse;width:100%;margin-top:1rem}} td,th{{border-bottom:1px solid #ddd;padding:.4rem;text-align:left;vertical-align:top}}
.pass{{color:#11734b}} .fail{{color:#b3261e;font-weight:600}} .score{{font-size:2.4rem;font-weight:700}} small{{color:#666}}
</style></head><body><h1>AI visibility check</h1>
<p>Paste an article link. The page, <code>/robots.txt</code> and <code>/llms.txt</code> are fetched once and checked.</p>
<form><input name="url" placeholder="https://..." value="{url}" autofocus><button>Check</button></form>{result}
<p><small>Checks follow public crawler and structured-data guidance; they are a checklist, not a prediction of any engine's ranking.</small></p></body></html>"""


def render(url):
    if not url:
        return PAGE.format(url="", result="")
    if not url.startswith(("http://", "https://")):
        return PAGE.format(url=html.escape(url), result="<p class=fail>Enter an http(s) link.</p>")
    try:
        checks = audit(url)
    except Exception as e:
        return PAGE.format(url=html.escape(url), result=f"<p class=fail>{html.escape(str(e))}</p>")
    rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td class={'pass' if ok or not w else 'fail'}>{'info' if not w else ('pass' if ok else 'fail')}</td>"
        f"<td>{html.escape(str(d))}{'' if ok or not w else '<br><small>' + html.escape(FIX[n]) + '</small>'}</td></tr>"
        for n, w, ok, d in checks)
    result = (f"<p class=score>{score(checks)}/100</p><table><tr><th>Check</th><th></th><th>Detail / fix</th></tr>"
              f"{rows}</table>")
    return PAGE.format(url=html.escape(url), result=result)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        body = render(q.get("url", [""])[0].strip()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("Open http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()

"""Score how ready a page is to be found and cited by AI answer engines.

    python3 -m geo.audit data/site/structured/passport-renewal.html
    python3 -m geo.audit https://example.com/some-article   # fetches the page and /robots.txt, /llms.txt

Checks are deterministic and each has a weight; the score is the weighted share passed.
They follow public guidance for AI crawlers and structured data, not any engine's secret
ranking, so treat the score as a checklist, not a prediction. "Answer in the first paragraph"
is a heuristic: the lead must be short, share words with the headline and contain a concrete
figure (a number, date, time or amount); a lead with no figure can still be a good answer.
"""
import gzip
import json
import re
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

# Bots that fetch pages to answer a user's question or build an AI search index.
AI_ANSWER_BOTS = ["OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Claude-User"]
# Bots (or robots.txt tokens) that collect pages for model training. Blocking them is a
# licensing decision, not a visibility mistake, so it is reported but not scored.
AI_TRAINING_BOTS = ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot"]
STOP = set("a an the of in on for to and or is are was be by with how what when from does do".split())
UA = "ai-visibility-lab/0.1 (+https://github.com/oguzhanozfe/ai-visibility-lab)"


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.h1, self.h2, self.paragraphs, self.jsonld = "", [], [], [], []
        self.canonical = self.has_time = False
        self.meta_date = False
        self._tag, self._buf, self._script_ld = None, [], False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("title", "h1", "h2", "p"):
            self._tag, self._buf = tag, []
        if tag == "script" and a.get("type") == "application/ld+json":
            self._script_ld, self._buf = True, []
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = True
        if (tag == "time" and a.get("datetime")) or (a.get("itemprop") or "").lower() == "datepublished":
            self.has_time = True
        if tag == "meta" and (a.get("property") or a.get("name") or "").lower() in (
                "article:published_time", "datepublished", "date", "pubdate"):
            self.meta_date = True

    def handle_data(self, data):
        if self._tag or self._script_ld:
            self._buf.append(data)

    def handle_endtag(self, tag):
        text = " ".join("".join(self._buf).split())
        if self._script_ld and tag == "script":
            self.jsonld.append(text)
            self._script_ld = False
        elif tag == self._tag:
            {"title": lambda: setattr(self, "title", text), "h1": lambda: self.h1.append(text),
             "h2": lambda: self.h2.append(text), "p": lambda: self.paragraphs.append(text)}[tag]()
            self._tag = None


def _words(text):
    # ponytail: 5-letter prefix as a crude stem so Turkish suffixes match (Netanyahu'dan ~ Netanyahu);
    # swap for a real stemmer if overlap misfires.
    return [w[:5] for w in re.findall(r"\w+", text.lower()) if w not in STOP]


META_LINE = re.compile(r"^\W*\d{1,2}[./ ]\S+[./ ]\d{2,4}|güncellen|updated|published|yayınlanma|^by ", re.I)


ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "ReportageNewsArticle", "AnalysisNewsArticle",
                 "FAQPage", "Product", "HowTo", "LiveBlogPosting"}


def _items(data):
    """Flatten JSON-LD: lists, @graph containers, nested objects."""
    if isinstance(data, list):
        for x in data:
            yield from _items(x)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _items(data["@graph"])


def _schema(jsonld):
    for raw in jsonld:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for item in _items(data):
            types = item.get("@type")
            types = set(types) if isinstance(types, list) else {types}
            if types & ARTICLE_TYPES:
                return item
    return None


def check_page(html, robots_txt=None, llms_txt=None, path="/"):
    """Returns a list of (check, weight, passed, detail)."""
    p = _Page()
    p.feed(html)
    schema = _schema(p.jsonld)
    first = next((x for x in p.paragraphs if len(x.split()) > 8 and not META_LINE.search(x[:60])), "")
    title_words = set(_words(p.h1[0] if p.h1 else p.title))
    overlap = len(title_words & set(_words(first)))
    blocked, blocked_training = [], []
    if robots_txt is not None:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_txt.splitlines())
        blocked = [b for b in AI_ANSWER_BOTS if not rp.can_fetch(b, path)]
        blocked_training = [b for b in AI_TRAINING_BOTS if not rp.can_fetch(b, path)]
    text_words = sum(len(x.split()) for x in p.paragraphs)
    checks = [
        ("AI answer bots allowed in robots.txt", 3, robots_txt is not None and not blocked,
         "robots.txt not checked" if robots_txt is None else ("blocked: " + ", ".join(blocked) if blocked else "all allowed")),
        ("AI training bots (info, not scored)", 0, not blocked_training,
         "robots.txt not checked" if robots_txt is None else
         ("blocked: " + ", ".join(blocked_training) if blocked_training else "all allowed")),
        ("llms.txt present", 1, bool(llms_txt), "found" if llms_txt else "missing"),
        ("Structured data (JSON-LD)", 2, schema is not None, schema.get("@type") if schema else "none"),
        ("Schema has headline, date and author", 2,
         bool(schema and schema.get("headline") and schema.get("datePublished") and schema.get("author")), ""),
        ("Publish date in the page", 1, bool(p.has_time or p.meta_date or (schema and schema.get("datePublished"))),
         "time tag" if p.has_time else ("meta tag" if p.meta_date else ("schema" if schema and schema.get("datePublished") else "none"))),
        ("One H1", 1, len(p.h1) == 1, f"{len(p.h1)} found"),
        ("Answer in the first paragraph", 3,
         0 < len(first.split()) <= 60 and overlap >= 2 and bool(re.search(r"\d", first)),
         f"{len(first.split())} words, {overlap} title words, "
         f"{'has' if re.search(r'[0-9]', first) else 'no'} concrete figure"),
        ("Question-style subheading", 1, any(h.endswith("?") for h in p.h2), ""),
        ("Text present in the HTML", 2, text_words >= 40, f"{text_words} words"),
        ("Canonical link", 1, p.canonical, ""),
    ]
    return checks


def score(checks):
    total = sum(w for _, w, _, _ in checks)
    return round(100 * sum(w for _, w, ok, _ in checks if ok) / total)


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain,*/*",
                                               "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            charset = r.headers.get_content_charset() or "utf-8"
            return body.decode(charset, "replace")
    except Exception:
        return None


def audit(target):
    """target: a local .html file (robots.txt / llms.txt read from the same folder) or an http(s) URL."""
    if target.startswith(("http://", "https://")):
        parts = urllib.parse.urlsplit(target)
        base = f"{parts.scheme}://{parts.netloc}"
        html = _fetch(target)
        if html is None:
            raise RuntimeError("could not fetch " + target + " (blocked, offline or not HTML)")
        robots, llms = _fetch(base + "/robots.txt"), _fetch(base + "/llms.txt")
        # Some servers answer missing files with an HTML page and status 200; that is not a real file.
        robots = None if robots and robots.lstrip().startswith("<") else robots
        llms = None if llms and llms.lstrip().startswith("<") else llms
        return check_page(html, robots, llms, parts.path or "/")
    f = Path(target)
    robots, llms = f.parent / "robots.txt", f.parent / "llms.txt"
    return check_page(f.read_text(), robots.read_text() if robots.exists() else None,
                      llms.read_text() if llms.exists() else None, "/" + f.name)


def report(target, checks):
    lines = [f"## {target}", f"Score: **{score(checks)}/100**", "", "| Check | Weight | Result | Detail |", "|---|---:|---|---|"]
    lines += [f"| {n} | {w} | {'info' if w == 0 else ('pass' if ok else 'FAIL')} | {d} |" for n, w, ok, d in checks]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python3 -m geo.audit <file.html | url> [...]")
    for t in sys.argv[1:]:
        print(report(t, audit(t)) + "\n")

"""Count AI crawler visits in a web server access log and check them against robots.txt.

    python3 -m geo.logs access.log robots.txt
    python3 -m geo.logs --demo        # made-up log against the synthetic site's robots.txt

Reads the common "combined" log format. A bot is identified by its user-agent string,
which anyone can fake; production use should also verify the published IP ranges.
"""
import collections
import random
import re
import sys
import urllib.robotparser
from datetime import datetime, timedelta

BOTS = {  # user-agent token: (operator, purpose)
    "GPTBot": ("OpenAI", "training"),
    "OAI-SearchBot": ("OpenAI", "search answers"),
    "ChatGPT-User": ("OpenAI", "user-triggered fetch"),
    "ClaudeBot": ("Anthropic", "training"),
    "Claude-User": ("Anthropic", "user-triggered fetch"),
    "PerplexityBot": ("Perplexity", "search answers"),
    "CCBot": ("Common Crawl", "open dataset"),
    "Bytespider": ("ByteDance", "training"),
    "Googlebot": ("Google", "search index"),
    "bingbot": ("Microsoft", "search index"),
}
LINE = re.compile(r'(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) [^"]*" '
                  r'(?P<status>\d{3}) \S+ "[^"]*" "(?P<ua>[^"]*)"')


def bot_of(ua):
    for token in BOTS:
        if token.lower() in ua.lower():
            return token
    return None


def analyze(lines, robots_txt=None):
    rp = None
    if robots_txt is not None:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(robots_txt.splitlines())
    hits = collections.Counter()
    pages = collections.defaultdict(collections.Counter)
    ignored = collections.Counter()
    humans = 0
    for line in lines:
        m = LINE.match(line)
        if not m:
            continue
        bot = bot_of(m["ua"])
        if not bot:
            humans += 1
            continue
        hits[bot] += 1
        pages[bot][m["path"]] += 1
        if rp is not None and not rp.can_fetch(bot, m["path"]):
            ignored[bot] += 1
    return {"humans": humans, "hits": hits, "pages": pages, "ignored_robots": ignored}


def report(result):
    total = result["humans"] + sum(result["hits"].values())
    out = [f"Requests: {total} ({result['humans']} not from known bots)", "",
           "| Bot | Operator | Purpose | Requests | Share | Distinct pages | Hits on disallowed paths |",
           "|---|---|---|---:|---:|---:|---:|"]
    for bot, n in result["hits"].most_common():
        op, purpose = BOTS[bot]
        out.append(f"| {bot} | {op} | {purpose} | {n} | {100 * n / total:.1f}% | {len(result['pages'][bot])} | "
                   f"{result['ignored_robots'].get(bot, 0)} |")
    return "\n".join(out)


def synthetic_log(paths, n=4000, seed=11):
    """A made-up access log so the analyzer can be shown without real traffic."""
    rng = random.Random(seed)
    uas = [("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1", 60),
           ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36", 25),
           ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", 6),
           ("Mozilla/5.0 (compatible; bingbot/2.0)", 2),
           ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2", 3),
           ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", 1.5),
           ("Mozilla/5.0 (compatible; PerplexityBot/1.0)", 1),
           ("CCBot/2.0 (https://commoncrawl.org/faq/)", 1),
           ("Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)", 0.5)]
    start = datetime(2026, 10, 1)
    out = []
    for i in range(n):
        ua = rng.choices([u for u, _ in uas], weights=[w for _, w in uas])[0]
        ts = (start + timedelta(seconds=i * 640 + rng.randint(0, 600))).strftime("%d/%b/%Y:%H:%M:%S +0000")
        ip = "10.{}.{}.{}".format(rng.randint(0, 255), rng.randint(0, 255), rng.randint(1, 254))
        out.append(f'{ip} - - [{ts}] "GET {rng.choice(paths)} HTTP/1.1" 200 5120 "-" "{ua}"')
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        from geo.site import SITE, TOPICS, build
        build()
        paths = [f"/{t[0]}.html" for t in TOPICS]
        print(report(analyze(synthetic_log(paths), (SITE / "baseline" / "robots.txt").read_text())))
        print("\n(Synthetic log: the bot mix and the robots.txt violations are made up for the demo.)")
        sys.exit()
    if len(sys.argv) < 2:
        sys.exit("usage: python3 -m geo.logs access.log [robots.txt] | python3 -m geo.logs --demo")
    robots = open(sys.argv[2]).read() if len(sys.argv) > 2 else None
    with open(sys.argv[1], errors="replace") as f:
        print(report(analyze(f, robots)))

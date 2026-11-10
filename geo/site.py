"""Build a small synthetic website in two versions of the same facts.

Every fact is about a fictional town (Northvale), so a language model cannot answer
from memory: it has to use the pages. Each topic gets two pages with identical facts:

  baseline  - long intro, answer buried in the fourth paragraph, no date, author or schema
  structured - answer in the first paragraph, question-style heading, visible date and
               author, JSON-LD Article markup

The baseline site's robots.txt also blocks two AI training bots and two AI answer bots,
and the site has no llms.txt.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "data" / "site"

# (slug, title subject, question, answer sentence, words that must appear in a correct answer)
TOPICS = [
    ("passport-renewal", "passport renewal",
     "How long does a passport renewal take in Northvale?",
     "A standard passport renewal in Northvale takes 18 working days; the express service takes 5 working days and costs 240 NVD.",
     ["18", "working days"]),
    ("library-card", "library cards",
     "From what age can a child get a Northvale library card?",
     "Children can get their own Northvale library card from age 7; the card is free and a replacement costs 6 NVD.",
     ["7"]),
    ("night-bus", "the N4 night bus",
     "How often does the N4 night bus run in Northvale?",
     "The N4 night bus runs every 25 minutes between 23:30 and 04:10.",
     ["25 minutes"]),
    ("glass-recycling", "glass recycling",
     "When is glass collected for recycling in Northvale?",
     "Glass is collected on the second Tuesday of every month.",
     ["second Tuesday"]),
    ("parking-permit", "residential parking permits",
     "How much is a residential parking permit in Northvale?",
     "A residential parking permit costs 42 NVD per year; a visitor permit costs 3 NVD per day.",
     ["42"]),
    ("marathon", "the Northvale Marathon",
     "What is the time limit for the Northvale Marathon?",
     "The 2027 Northvale Marathon is on 18 April and runners must finish within 6 hours 30 minutes.",
     ["6 hours 30 minutes"]),
    ("tap-water", "tap water hardness",
     "How hard is Northvale tap water?",
     "Northvale tap water has a hardness of 182 mg/L, which is classed as moderately hard.",
     ["182"]),
    ("harbor-museum", "Harbor Museum opening hours",
     "When is the Harbor Museum in Northvale open?",
     "The Harbor Museum is open from 10:00 to 17:00, is closed on Mondays and is free on the first Sunday of each month.",
     ["10:00", "17:00"]),
    ("bike-share", "bike share prices",
     "How much does the Northvale bike share cost?",
     "The first 30 minutes of a bike share ride are free; after that each 15 minutes costs 1.5 NVD.",
     ["30 minutes", "1.5"]),
    ("school-enrolment", "school enrolment",
     "What is the school enrolment deadline in Northvale?",
     "The school enrolment deadline is 14 March; parents need a proof of address and the child's vaccination record.",
     ["14 March"]),
    ("gull-island-ferry", "the Gull Island ferry",
     "When is the last ferry back from Gull Island in winter?",
     "The Gull Island ferry crossing takes 35 minutes and the last winter return leaves at 19:45.",
     ["19:45"]),
    ("construction-noise", "construction noise rules",
     "When is construction work allowed in Northvale?",
     "Construction work is allowed from 08:00 to 18:00 on weekdays and from 09:00 to 13:00 on Saturdays.",
     ["08:00", "18:00"]),
]

FILLER = [
    "Residents often ask us about {s}. It is one of those topics that comes up again and again, "
    "and the rules have changed a few times over the years, so it is worth taking a moment to look at the background.",
    "Northvale has grown quickly, and with growth come new services and new questions. "
    "Many people first hear about {s} from neighbours, and not everything they hear is accurate.",
    "Before we get to the details, it helps to understand why {s} matters to so many households "
    "and how the town council thinks about it when planning the year ahead.",
]

AI_BOTS_BLOCKED = ["GPTBot", "CCBot", "OAI-SearchBot", "PerplexityBot"]


def _page(title, body_html, head_extra=""):
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title>{head_extra}</head>\n<body>\n{body_html}\n</body></html>\n"
    )


def baseline_page(slug, subject, question, answer):
    paras = [f.format(s=subject) for f in FILLER]
    paras.append("After all of that, here is the part most people are looking for. " + answer)
    body = f"<h1>Everything you need to know about {subject}</h1>\n" + "\n".join(f"<p>{p}</p>" for p in paras)
    return _page(f"Everything you need to know about {subject}", body)


def structured_page(slug, subject, question, answer, date="2026-10-01", author="Northvale Desk"):
    title = question.rstrip("?")
    schema = {
        "@context": "https://schema.org", "@type": "Article", "headline": title,
        "datePublished": date, "author": {"@type": "Organization", "name": author},
    }
    head = f'<link rel="canonical" href="https://structured.example/{slug}.html">' \
           f'<script type="application/ld+json">{json.dumps(schema)}</script>'
    body = (
        f"<h1>{title}</h1>\n<p class=\"byline\">By {author} · <time datetime=\"{date}\">{date}</time></p>\n"
        f"<p>{answer}</p>\n<h2>{question}</h2>\n"
        f"<p>{FILLER[0].format(s=subject)}</p>"
    )
    return _page(title, body, head)


def build(out=SITE):
    for variant in ("baseline", "structured"):
        (out / variant).mkdir(parents=True, exist_ok=True)
    for slug, subject, question, answer, _ in TOPICS:
        (out / "baseline" / f"{slug}.html").write_text(baseline_page(slug, subject, question, answer))
        (out / "structured" / f"{slug}.html").write_text(structured_page(slug, subject, question, answer))
    blocked = "".join(f"User-agent: {b}\nDisallow: /\n\n" for b in AI_BOTS_BLOCKED)
    (out / "baseline" / "robots.txt").write_text(blocked + "User-agent: *\nAllow: /\n")
    (out / "structured" / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    (out / "structured" / "llms.txt").write_text(
        "# Northvale Desk\n\n> Plain answers about Northvale town services.\n\n## Pages\n"
        + "".join(f"- [{q.rstrip('?')}](https://structured.example/{s}.html)\n" for s, _, q, _, _ in TOPICS))
    return out


if __name__ == "__main__":
    print("Wrote", build())

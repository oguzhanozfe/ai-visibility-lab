"""Which version of the same facts does an AI answer engine cite?

Two stages, measured separately:

1. Retrieval: all 24 pages go into a SQLite FTS5 (BM25) index. For each question we record
   where the baseline and the structured page rank.
2. Generation: a local model gets the baseline page, the structured page and two pages about
   other topics, in a shuffled order, and must answer with citations. Every question runs twice,
   once with the baseline page placed before the structured one and once after, so position
   bias cancels out.

    python3 experiment/run.py                  # qwen3.5:9b and qwen3.5:4b through Ollama
    LLM_MODELS=qwen3.5:9b python3 experiment/run.py

Writes docs/RESULTS.md and data/experiment.json.
"""
import json
import os
import random
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo.audit import _Page, audit, score  # noqa: E402
from geo.site import SITE, TOPICS, build  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.environ.get("LLM_API_KEY", "ollama")
MODELS = os.environ.get("LLM_MODELS", "qwen3.5:9b,qwen3.5:4b").split(",")
SYSTEM = ("You are a search answer engine. Answer the user's question in one or two sentences using only "
          "the numbered sources. Cite the sources you used by number. Reply as JSON: "
          '{"answer": "...", "citations": [numbers]}. If no source answers the question, '
          'reply {"answer": "not found", "citations": []}.')


def page_text(path):
    p = _Page()
    p.feed(path.read_text())
    return "\n".join([p.h1[0] if p.h1 else p.title] + p.paragraphs)


def load_pages():
    pages = {}
    for variant in ("baseline", "structured"):
        for slug, *_ in TOPICS:
            pages[(slug, variant)] = page_text(SITE / variant / f"{slug}.html")
    return pages


def bm25_ranks(pages, question):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE p USING fts5(slug, variant, body)")
    con.executemany("INSERT INTO p VALUES (?, ?, ?)", [(s, v, t) for (s, v), t in pages.items()])
    terms = " OR ".join(sorted(set(re.findall(r"[a-z0-9]{3,}", question.lower()))))
    rows = con.execute("SELECT slug, variant FROM p WHERE p MATCH ? ORDER BY bm25(p)", (terms,)).fetchall()
    return {row: i + 1 for i, row in enumerate(rows)}


def chat(model, sources, question, retries=2):
    """Thinking models in JSON mode sometimes return an empty message; retry those."""
    for _ in range(retries + 1):
        answer, cites = _chat_once(model, sources, question)
        if answer.strip():
            break
    return answer, cites


def _chat_once(model, sources, question):
    ctx = "\n\n".join(f"[{i + 1}]\n{s}" for i, s in enumerate(sources))
    body = json.dumps({"model": model, "temperature": 0, "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": f"Sources:\n{ctx}\n\nQuestion: {question}"}]}).encode()
    req = urllib.request.Request(BASE_URL.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + API_KEY})
    with urllib.request.urlopen(req, timeout=300) as r:
        content = json.load(r)["choices"][0]["message"]["content"] or ""
    try:
        out = json.loads(content[content.find("{"):content.rfind("}") + 1])
    except ValueError:
        out = {"answer": content, "citations": []}
    cites = set()
    for c in out.get("citations") or []:
        try:
            cites.add(int(c))
        except (TypeError, ValueError):
            pass
    return str(out.get("answer", "")), cites


def trials(pages, rng):
    """For each topic, two orders: baseline before structured, and after."""
    slugs = [t[0] for t in TOPICS]
    for slug, _, question, _, keys in TOPICS:
        others = rng.sample([s for s in slugs if s != slug], 2)
        distractors = [pages[(o, rng.choice(["baseline", "structured"]))] for o in others]
        for baseline_first in (True, False):
            pair = [("baseline", pages[(slug, "baseline")]), ("structured", pages[(slug, "structured")])]
            if not baseline_first:
                pair.reverse()
            slots = [("distractor", distractors[0])] + pair + [("distractor", distractors[1])]
            yield slug, question, keys, baseline_first, slots


def run(models=MODELS, seed=3):
    build()
    pages = load_pages()
    results = {"retrieval": [], "generation": {}}
    for slug, _, question, _, _ in TOPICS:
        ranks = bm25_ranks(pages, question)
        results["retrieval"].append({"slug": slug, "baseline": ranks.get((slug, "baseline")),
                                     "structured": ranks.get((slug, "structured"))})
    for model in models:
        rows = []
        for slug, question, keys, baseline_first, slots in trials(pages, random.Random(seed)):
            answer, cites = chat(model, [t for _, t in slots], question)
            cited = {slots[c - 1][0] for c in cites if 1 <= c <= len(slots)}
            rows.append({"slug": slug, "baseline_first": baseline_first, "answer": answer,
                         "cited_baseline": "baseline" in cited, "cited_structured": "structured" in cited,
                         "cited_distractor": "distractor" in cited,
                         "empty": not answer.strip(),
                         "correct": all(k.lower() in answer.lower() for k in keys)})
            print(model, slug, "B-first" if baseline_first else "S-first", sorted(cited), "ok" if rows[-1]["correct"] else "WRONG")
        results["generation"][model] = rows
    audits = {v: score(audit(str(SITE / v / f"{TOPICS[0][0]}.html"))) for v in ("baseline", "structured")}
    results["audit_scores"] = audits
    (ROOT / "data" / "experiment.json").write_text(json.dumps(results, indent=1))
    write_report(results)
    return results


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "-"


def write_report(r):
    ret = r["retrieval"]
    s_better = sum(1 for x in ret if x["structured"] and (not x["baseline"] or x["structured"] < x["baseline"]))
    lines = ["# Results", "",
             "Synthetic site, 12 topics, two versions of each page with the same facts. All numbers are from one run "
             "with temperature 0; small samples, read them as direction, not as effect sizes.", "",
             f"Audit score of a typical page: baseline **{r['audit_scores']['baseline']}/100**, "
             f"structured **{r['audit_scores']['structured']}/100**.", "",
             "## 1. Retrieval (BM25)", "",
             f"The structured page ranked above the baseline page for **{s_better} of {len(ret)}** questions.", "",
             "| Topic | Baseline rank | Structured rank |", "|---|---:|---:|"]
    lines += [f"| {x['slug']} | {x['baseline']} | {x['structured']} |" for x in ret]
    lines += ["", "## 2. Generation (which source the model cites)", "",
              "Each topic is asked twice: baseline page placed first, then structured page placed first.", "",
              "Shares are of trials with a non-empty answer; empty outputs (the model returned nothing even after "
              "two retries) are counted separately.", "",
              "| Model | Trials | Empty outputs | Cited structured | Cited baseline | Cited both | Cited a distractor | Correct answer |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for model, all_rows in r["generation"].items():
        rows = [x for x in all_rows if not x.get("empty")]
        n = len(rows)
        lines.append(f"| {model} | {len(all_rows)} | {len(all_rows) - n} | {pct(sum(x['cited_structured'] for x in rows), n)} | "
                     f"{pct(sum(x['cited_baseline'] for x in rows), n)} | "
                     f"{pct(sum(x['cited_structured'] and x['cited_baseline'] for x in rows), n)} | "
                     f"{pct(sum(x['cited_distractor'] for x in rows), n)} | {pct(sum(x['correct'] for x in rows), n)} |")
    lines += ["", "Position check (share of trials citing the page that was placed first of the pair):", ""]
    for model, all_rows in r["generation"].items():
        rows = [x for x in all_rows if not x.get("empty")]
        first = sum((x["cited_baseline"] if x["baseline_first"] else x["cited_structured"]) for x in rows)
        second = sum((x["cited_structured"] if x["baseline_first"] else x["cited_baseline"]) for x in rows)
        lines.append(f"- {model}: first of the pair cited in {pct(first, len(rows))}, second in {pct(second, len(rows))}.")
    lines += ["", "## 3. Crawler access", "",
              "The baseline robots.txt blocks OAI-SearchBot and PerplexityBot. An engine that respects robots.txt "
              "never fetches those pages, so in that engine the baseline site has zero chance of being cited, "
              "whatever its content. That is the largest effect here and it needs no model to measure.", "",
              "## Limits", "",
              "- Real answer engines combine their own index, ranking and models; this lab isolates two stages with "
              "one retriever and small local models.",
              "- The structured page is also shorter, so length and structure are not separated here.",
              "- 12 topics x 2 orders is a small sample."]
    (ROOT / "docs" / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    run()

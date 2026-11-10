# ai-visibility-lab

Will AI answer engines find and cite your pages? This lab checks a page against the things
AI crawlers and answer engines can actually see, counts AI bot traffic in your server logs,
and runs a small experiment on how page structure changes which source a model cites.

Standard library Python and SQLite only. The experiment uses local models through Ollama,
so nothing leaves your machine.

[![CI](https://github.com/oguzhanozfe/ai-visibility-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/oguzhanozfe/ai-visibility-lab/actions/workflows/ci.yml)

## Run it

```bash
python3 -m geo.web                     # open http://127.0.0.1:8765, paste a link, get a score
python3 -m geo.audit https://example.com/some-article
python3 -m geo.logs access.log robots.txt
python3 -m geo.logs --demo             # made-up log, to see the report
python3 -m unittest discover -s tests -v
python3 experiment/run.py              # needs Ollama with qwen3.5:9b / qwen3.5:4b, or set LLM_MODELS
```

Python 3.9 or newer. Any OpenAI-compatible endpoint can stand in for Ollama (`LLM_BASE_URL`, `LLM_API_KEY`).

## 1. Page audit

[`geo/audit.py`](geo/audit.py) fetches the page plus `/robots.txt` and `/llms.txt` and runs weighted checks:

| Check | Weight | Why |
|---|---:|---|
| AI answer bots allowed in robots.txt (OAI-SearchBot, ChatGPT-User, PerplexityBot, Claude-User) | 3 | A blocked answer bot never fetches the page, so the page cannot be cited there |
| AI training bots (GPTBot, ClaudeBot, Google-Extended, CCBot) | info | Blocking training is a licensing choice, so it is reported but not scored |
| `llms.txt` present | 1 | A plain index of the pages worth reading |
| JSON-LD Article / NewsArticle / Product / FAQ (lists and `@graph` handled) | 2 | Machine-readable title, date and author |
| Schema has headline, date and author | 2 | Freshness and attribution |
| Publish date in the page (`<time>` or meta tag) | 1 | |
| One H1 | 1 | |
| Answer in the first paragraph | 3 | Short lead that shares words with the headline and contains a concrete figure |
| Question-style subheading | 1 | Matches how people ask |
| Text present in the HTML | 2 | Pages that render only through JavaScript are often invisible to crawlers |
| Canonical link | 1 | |

The score is the weighted share of checks passed. It is a checklist built from public crawler and
structured-data guidance, not a model of any engine's ranking. [`geo/web.py`](geo/web.py) wraps the
same audit in a one-page local web app with a fix for every failed check.

## 2. AI bot traffic

[`geo/logs.py`](geo/logs.py) reads a combined-format access log and reports, per bot: operator,
purpose (training, search answers, user-triggered fetch, search index), requests, share of traffic,
distinct pages, and requests to paths that robots.txt disallows for that bot. This answers two
questions a publisher or a shop now asks: which AI companies read our pages, and do they respect
our rules? User agents can be faked; check the operators' published IP ranges before acting.

## 3. Experiment: does structure change what gets cited?

[`geo/site.py`](geo/site.py) builds a synthetic site about a fictional town, so a model cannot answer
from memory. Each of 12 topics has two pages with **identical facts**:

- **baseline**: long intro, the answer in the fourth paragraph, no date, author or schema; its robots.txt blocks two answer bots and two training bots.
- **structured**: the answer in the first paragraph, a question-style subheading, visible date and author, JSON-LD.

[`experiment/run.py`](experiment/run.py) measures two stages separately:

1. **Retrieval**: all 24 pages in a SQLite FTS5 (BM25) index; where does each version rank for the question?
2. **Generation**: a local model gets both versions plus two unrelated pages and must answer with citations. Each question runs twice, with the baseline placed before and after the structured page, so position bias cancels out.

### Results (one run, [full table](docs/RESULTS.md))

- **Audit:** baseline page 18/100, structured page 100/100.
- **Retrieval:** the structured page ranked above the baseline page for 12 of 12 questions.
- **Generation:** once both pages were in the context, the models cited both almost every time (qwen3.5:9b 94%, qwen3.5:4b 100% of non-empty answers), never cited a distractor, and every answer was correct. Placing a page first in the pair made no measurable difference. qwen3.5:9b returned an empty answer in 6 of 24 trials even after retries; those are counted separately.
- **Access:** the baseline robots.txt blocks OAI-SearchBot and PerplexityBot, so an engine that respects it never fetches those pages at all.

So in this setup, structure mattered at the retrieval step and robots.txt decided whether the page could be found at all. Once the page reached the model, the structure made no difference to whether it was cited.

## Limits

- Real answer engines have their own index, ranking and models. The lab isolates two stages with one retriever and small local models; it shows a direction, not the size of the effect on any real engine.
- The structured page is also shorter, so length and structure are not separated.
- The audit is heuristic. "Answer in the first paragraph" can miss a good lead without a number.

Built with Claude Code as a coding assistant.

## License

MIT

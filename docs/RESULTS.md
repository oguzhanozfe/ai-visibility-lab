# Results

Synthetic site, 12 topics, two versions of each page with the same facts. All numbers are from one run with temperature 0; small samples, read them as direction, not as effect sizes.

Audit score of a typical page: baseline **18/100**, structured **100/100**.

## 1. Retrieval (BM25)

The structured page ranked above the baseline page for **12 of 12** questions.

| Topic | Baseline rank | Structured rank |
|---|---:|---:|
| passport-renewal | 2 | 1 |
| library-card | 2 | 1 |
| night-bus | 2 | 1 |
| glass-recycling | 2 | 1 |
| parking-permit | 2 | 1 |
| marathon | 2 | 1 |
| tap-water | 2 | 1 |
| harbor-museum | 2 | 1 |
| bike-share | 2 | 1 |
| school-enrolment | 2 | 1 |
| gull-island-ferry | 2 | 1 |
| construction-noise | 2 | 1 |

## 2. Generation (which source the model cites)

Each topic is asked twice: baseline page placed first, then structured page placed first.

Shares are of trials with a non-empty answer; empty outputs (the model returned nothing even after two retries) are counted separately.

| Model | Trials | Empty outputs | Cited structured | Cited baseline | Cited both | Cited a distractor | Correct answer |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3.5:9b | 24 | 6 | 100% | 94% | 94% | 0% | 100% |
| qwen3.5:4b | 24 | 1 | 100% | 100% | 100% | 0% | 100% |

Position check (share of trials citing the page that was placed first of the pair):

- qwen3.5:9b: first of the pair cited in 100%, second in 94%.
- qwen3.5:4b: first of the pair cited in 100%, second in 100%.

## 3. Crawler access

The baseline robots.txt blocks OAI-SearchBot and PerplexityBot. An engine that respects robots.txt never fetches those pages, so in that engine the baseline site has zero chance of being cited, whatever its content. That is the largest effect here and it needs no model to measure.

## Limits

- Real answer engines combine their own index, ranking and models; this lab isolates two stages with one retriever and small local models.
- The structured page is also shorter, so length and structure are not separated here.
- 12 topics x 2 orders is a small sample.

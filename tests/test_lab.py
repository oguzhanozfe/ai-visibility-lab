import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo import audit, logs, site  # noqa: E402
from geo.web import render  # noqa: E402


def check(checks, name):
    return next(ok for n, _, ok, _ in checks if n == name)


class AuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        site.build(cls.dir)

    def page(self, variant):
        return audit.audit(str(self.dir / variant / "passport-renewal.html"))

    def test_structured_scores_full_marks(self):
        self.assertEqual(audit.score(self.page("structured")), 100)

    def test_baseline_fails_answer_first_and_answer_bots(self):
        c = self.page("baseline")
        self.assertFalse(check(c, "Answer in the first paragraph"))
        self.assertFalse(check(c, "AI answer bots allowed in robots.txt"))
        self.assertLess(audit.score(c), 40)

    def test_training_bots_are_reported_but_not_scored(self):
        html = (self.dir / "structured" / "passport-renewal.html").read_text()
        blocked = audit.check_page(html, "User-agent: GPTBot\nDisallow: /\n", "x")
        self.assertEqual(audit.score(blocked), 100)
        self.assertFalse(check(blocked, "AI training bots (info, not scored)"))

    def test_jsonld_inside_graph_and_type_list(self):
        html = ('<html><head><script type="application/ld+json">{"@graph":[{"@type":"WebPage"},'
                '{"@type":["NewsArticle"],"headline":"h","datePublished":"2026-01-01","author":{"name":"a"}}]}'
                '</script></head><body><h1>h</h1></body></html>')
        c = audit.check_page(html)
        self.assertTrue(check(c, "Structured data (JSON-LD)"))
        self.assertTrue(check(c, "Schema has headline, date and author"))

    def test_meta_date_counts(self):
        c = audit.check_page('<meta property="article:published_time" content="2026-01-01"><h1>x</h1>')
        self.assertTrue(check(c, "Publish date in the page"))

    def test_web_rejects_non_http(self):
        self.assertIn("http(s)", render("file:///etc/passwd"))


class LogsTest(unittest.TestCase):
    def test_counts_bots_and_robots_violations(self):
        lines = [
            '1.1.1.1 - - [01/Oct/2026:00:00:01 +0000] "GET /a.html HTTP/1.1" 200 10 "-" "Mozilla/5.0 GPTBot/1.2"',
            '1.1.1.2 - - [01/Oct/2026:00:00:02 +0000] "GET /a.html HTTP/1.1" 200 10 "-" "Mozilla/5.0 (iPhone)"',
            '1.1.1.3 - - [01/Oct/2026:00:00:03 +0000] "GET /b.html HTTP/1.1" 200 10 "-" "PerplexityBot/1.0"',
            'garbage line',
        ]
        r = logs.analyze(lines, "User-agent: GPTBot\nDisallow: /\n")
        self.assertEqual(r["humans"], 1)
        self.assertEqual(r["hits"]["GPTBot"], 1)
        self.assertEqual(r["ignored_robots"]["GPTBot"], 1)
        self.assertEqual(r["ignored_robots"].get("PerplexityBot", 0), 0)

    def test_synthetic_log_parses(self):
        r = logs.analyze(logs.synthetic_log(["/x.html"], n=300))
        self.assertEqual(r["humans"] + sum(r["hits"].values()), 300)


class ExperimentTest(unittest.TestCase):
    def test_trials_cover_both_orders_with_fake_model(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiment"))
        import random
        import run as exp
        site.build()
        pages = exp.load_pages()
        ts = list(exp.trials(pages, random.Random(0)))
        self.assertEqual(len(ts), 2 * len(site.TOPICS))
        orders = {t[3] for t in ts}
        self.assertEqual(orders, {True, False})
        for _, _, _, baseline_first, slots in ts:
            kinds = [k for k, _ in slots]
            self.assertEqual(kinds.index("baseline") < kinds.index("structured"), baseline_first)


if __name__ == "__main__":
    unittest.main()

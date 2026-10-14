"""Check price extraction and change detection on made-up pricing pages.

Run with: python3 -m unittest
"""
import re
import unittest

import monitor

MARKDOWN_TABLE = """# Pricing

## Text models

| Model | Input | Output |
|---|---|---|
| model-small | $0.10 | $0.40 |
| model-large | $2.00 | $8.00 |
| model-legacy | $2.00 | $8.00 |
"""

RENDERED_PAGE = """Example AI pricing

Standard plan

Input tokens
$0.25
Output tokens
$1.25

Batch plan

Input tokens
$0.125
Output tokens
$0.625

Promotions run until the end of the quarter. The batch discount applies to all models at $0.10 per million cached tokens.
"""

PAGES = {"markdown table": MARKDOWN_TABLE, "rendered page": RENDERED_PAGE}


class PriceLines(unittest.TestCase):
    def test_every_price_is_captured_with_its_labels(self):
        for name, page in PAGES.items():
            with self.subTest(page=name):
                lines = monitor.price_lines(page)
                found = re.findall(monitor.PRICE, "\n".join(lines))
                self.assertEqual(sorted(found),
                                 sorted(re.findall(monitor.PRICE, page)))
                self.assertTrue(all(" > " in line for line in lines))

    def test_each_single_price_edit_changes_the_snapshot(self):
        for name, page in PAGES.items():
            before = monitor.price_lines(page)
            prices = list(monitor.PRICE.finditer(page))
            for match in prices:
                edited = page[:match.start()] + "$9.99" + page[match.end():]
                with self.subTest(page=name, price=match.group()):
                    self.assertNotEqual(monitor.price_lines(edited), before)


class Checks(unittest.TestCase):
    ENTRY = {"id": "example", "expect_url_prefix": "https://example.com/pricing",
             "expect_text": ["## Text models"], "min_price_lines": 2}

    def problems(self, url, page):
        return monitor.check(self.ENTRY, url, page, monitor.price_lines(page))

    def test_the_watched_page_passes(self):
        self.assertEqual(
            self.problems("https://example.com/pricing", MARKDOWN_TABLE), [])

    def test_a_redirect_a_missing_label_and_a_missing_table_are_reported(self):
        self.assertTrue(self.problems("https://example.com/", MARKDOWN_TABLE))
        self.assertTrue(self.problems("https://example.com/pricing",
                                      MARKDOWN_TABLE.replace("## Text models", "")))
        self.assertTrue(self.problems("https://example.com/pricing",
                                      "# Pricing\n\nPage not found.\n"))


if __name__ == "__main__":
    unittest.main()

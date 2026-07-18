import unittest
from urllib.error import URLError

from services.web_supplement_service import parse_bing_results, parse_duckduckgo_results, search_web


class WebSupplementServiceTests(unittest.TestCase):
    def test_parse_duckduckgo_results(self):
        html = """
        <div class="result">
          <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fcache">Cache &amp; 映射</a>
          <a class="result__snippet">介绍 Cache 直接映射和组相联。</a>
        </div>
        """

        results = parse_duckduckgo_results(html)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Cache & 映射")
        self.assertEqual(results[0].url, "https://example.com/cache")
        self.assertIn("组相联", results[0].snippet)

    def test_parse_duckduckgo_lite_results(self):
        html = """
        <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Faov" class='result-link'>AOV 拓扑排序</a>
        <td class='result-snippet'>408 数据结构 AOV 网。</td>
        """

        results = parse_duckduckgo_results(html)

        self.assertEqual(results[0].title, "AOV 拓扑排序")
        self.assertEqual(results[0].url, "https://example.com/aov")
        self.assertIn("408", results[0].snippet)

    def test_search_web_uses_injected_fetcher(self):
        def fake_fetch(url):
            self.assertIn("Cache", url)
            return """
            <div class="result">
              <a class="result__a" href="https://example.com/a">A</a>
              <div class="result__snippet">Cache snippet</div>
            </div>
            """

        results = search_web("Cache 映射", fetch=fake_fetch)

        self.assertEqual(results[0]["title"], "A")

    def test_search_web_falls_back_after_timeout(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise URLError("timed out")
            return """
            <li class="b_algo">
              <h2><a href="https://example.com/b">Bing Result</a></h2>
              <p>Cache 组相联。</p>
            </li>
            """

        results = search_web("Cache 映射", fetch=fake_fetch)

        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(results[0]["title"], "Bing Result")

    def test_parse_bing_results(self):
        html = """
        <li class="b_algo">
          <h2><a href="https://example.com/cache">Cache</a></h2>
          <p>直接映射、组相联、全相联。</p>
        </li>
        """

        results = parse_bing_results(html)

        self.assertEqual(results[0].url, "https://example.com/cache")
        self.assertIn("组相联", results[0].snippet)


if __name__ == "__main__":
    unittest.main()

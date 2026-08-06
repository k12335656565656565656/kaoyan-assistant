import unittest

import fitz

from scripts.render_math_true_exam_screenshots import year_pages


class RenderMathTrueExamScreenshotTests(unittest.TestCase):
    def test_uses_year_bookmarks_to_create_non_overlapping_ranges(self):
        document = fitz.open()
        for _ in range(8):
            document.new_page()
        document.set_toc([[1, "2016", 1], [1, "2017", 4], [1, "2018", 7]])

        ranges = list(year_pages(document, 2016, 2018))

        self.assertEqual(ranges[0], (2016, range(0, 3)))
        self.assertEqual(ranges[1], (2017, range(3, 6)))
        self.assertEqual(ranges[2], (2018, range(6, 8)))
        document.close()


if __name__ == "__main__":
    unittest.main()

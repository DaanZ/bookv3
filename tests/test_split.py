"""How many parts a book is cut into when nobody chose."""
import unittest

from util.split import MAX_PARTS_PER_BOOK, default_parts, page_chunk_bounds


class DefaultParts(unittest.TestCase):
    def test_one_part_per_25_pages(self):
        self.assertEqual(default_parts(25), 1)
        self.assertEqual(default_parts(26), 2)
        self.assertEqual(default_parts(250), 10)

    def test_never_more_than_twenty(self):
        self.assertEqual(MAX_PARTS_PER_BOOK, 20)
        self.assertEqual(default_parts(821), 20)  # Godel, Escher, Bach was 33
        self.assertEqual(default_parts(5000), 20)

    def test_never_fewer_than_one(self):
        self.assertEqual(default_parts(0), 1)
        self.assertEqual(default_parts(3), 1)

    def test_twenty_parts_still_cover_every_page(self):
        bounds = page_chunk_bounds(821, default_parts(821))
        self.assertEqual((bounds[0][0], bounds[-1][1], len(bounds)), (0, 821, 20))
        self.assertTrue(all(a[1] == b[0] for a, b in zip(bounds, bounds[1:])))


if __name__ == "__main__":
    unittest.main()

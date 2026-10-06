import unittest

from dates import days_in_month, is_leap, parse_date


class TestDates(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_date("2024-03-15"), (2024, 3, 15))

    def test_rejects_bad_day(self):
        with self.assertRaises(ValueError):
            parse_date("2023-04-31")

    def test_leap_years(self):
        self.assertTrue(is_leap(2024))
        self.assertFalse(is_leap(2023))

    def test_century_years(self):
        self.assertFalse(is_leap(1900))
        self.assertTrue(is_leap(2000))
        self.assertEqual(days_in_month(2100, 2), 28)


if __name__ == "__main__":
    unittest.main()

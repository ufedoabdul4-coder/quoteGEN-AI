"""Classification tests.

These guard the one rule the whole quotation depends on: money must be provable
from the text, and a phone number, date, quantity or reference number must never
be mistaken for it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import classify as c


class PhoneBeforeMoneyTest(unittest.TestCase):
    def test_international_phone_is_not_money(self):
        for value in ("+234 803 000 0000", "+1 (415) 555-0199", "+44 20 7946 0958"):
            with self.subTest(value=value):
                self.assertTrue(c.is_phone(value))
                self.assertFalse(c.is_money(value))
                self.assertIsNone(c.parse_amount(value))

    def test_local_phone_is_not_money(self):
        self.assertTrue(c.is_phone("0803 456 7890"))
        self.assertFalse(c.is_money("0803 456 7890"))


class MoneyTest(unittest.TestCase):
    def test_marked_amounts(self):
        cases = {
            "$1,250.50": 1250.50,
            "NGN 450,000": 450000.0,
            "GBP 12,000": 12000.0,
            "EUR 3.500,00".replace(".", ","): None,  # euro style is out of scope
            "₦250,000": 250000.0,
            "₹1,20,000": None,
        }
        self.assertEqual(c.parse_amount("$1,250.50"), 1250.50)
        self.assertEqual(c.parse_amount("NGN 450,000"), 450000.0)
        self.assertEqual(c.parse_amount("£12,000"), 12000.0)
        self.assertEqual(c.parse_amount("₦250,000"), 250000.0)

    def test_bare_grouped_amounts(self):
        self.assertTrue(c.is_money("2,000,000"))
        self.assertTrue(c.is_money("450,000"))
        self.assertTrue(c.is_money("1,200.50"))
        self.assertEqual(c.parse_amount("2,000,000"), 2000000.0)

    def test_plain_integer_is_not_money_without_context(self):
        self.assertFalse(c.is_money("450000"))
        self.assertFalse(c.is_money("1200"))

    def test_prose_containing_numbers_is_not_money(self):
        self.assertFalse(c.is_money("Supply 3 units at 2,000 each"))
        self.assertFalse(c.is_money("About 12 rooms need work"))


class DateQuantityReferenceTest(unittest.TestCase):
    def test_dates(self):
        self.assertTrue(c.is_date("12/06/2026"))
        self.assertTrue(c.is_date("2026-06-12"))
        self.assertFalse(c.is_money("12/06/2026"))
        self.assertFalse(c.is_phone("12/06/2026"))

    def test_quantities(self):
        for value in ("50 bags", "12 units", "3 pax", "200 sqm", "8 hours"):
            with self.subTest(value=value):
                self.assertTrue(c.is_quantity(value))

    def test_references(self):
        for value in ("Quote #QT-2026-014", "Ref: ABC/2026/7", "Invoice INV-0093"):
            with self.subTest(value=value):
                self.assertTrue(c.is_reference(value))
                self.assertFalse(c.is_money(value))

    def test_amount_in_words(self):
        self.assertTrue(c.is_amount_in_words("One Hundred Thousand Naira only"))
        self.assertFalse(c.is_amount_in_words("Deep clean the kitchen"))


class CurrencyTest(unittest.TestCase):
    def test_currency_detection(self):
        self.assertEqual(c.currency_of("$1,000"), "USD")
        self.assertEqual(c.currency_of("₦250,000"), "NGN")
        self.assertEqual(c.currency_of("500 EUR"), "EUR")
        self.assertEqual(c.currency_of("nothing here"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

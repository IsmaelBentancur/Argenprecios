import unittest
import sys
import os

# Mock paths for imports
sys.path.append(os.path.abspath("C:/Users/Isma/Downloads/argenprecios"))

from modules.harvester.adapters.base_adapter import BaseAdapter
from modules.harvester.ean_utils import validate_gtin, is_internal_coto_id

class TestParsers(unittest.TestCase):
    def test_clean_price(self):
        cases = [
            ("$1.234,56", 1234.56),
            ("1234,56", 1234.56),
            ("$ 1.234,56", 1234.56),
            ("$12.900", 12900.0),
            ("$2.900,00", 2900.0),
            ("1.500,50", 1500.5),
            ("500", 500.0),
            ("Precio: $1.200,99", 1200.99),
            ("abc", None),
            ("", None),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(BaseAdapter.clean_price(raw), expected)

    def test_validate_gtin(self):
        # Valid GTIN-13 (GS1)
        self.assertTrue(validate_gtin("7790895007217")) 
        self.assertTrue(validate_gtin("7790895064661"))
        # Valid GTIN-8
        self.assertTrue(validate_gtin("12345670"))
        # Invalid check digit
        self.assertFalse(validate_gtin("7790895007218"))
        # Invalid length
        self.assertFalse(validate_gtin("1234567"))
        # Not numeric
        self.assertFalse(validate_gtin("ABC1234567890"))

    def test_is_internal_coto_id(self):
        # Coto internal usually 8 digits, fails GS1 check
        self.assertTrue(is_internal_coto_id("00566098"))
        # Real GTIN-13
        self.assertFalse(is_internal_coto_id("7790895007217"))

if __name__ == "__main__":
    unittest.main()


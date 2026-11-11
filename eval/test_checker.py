"""Unit tests for eval/checker.py. Run: venv/bin/python -m unittest eval.test_checker -v
(or: venv/bin/python eval/test_checker.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import checker as C  # noqa: E402

TEE = {"product_id": "TSHIRT-001", "product_name": "Everyday Organic Cotton Tee", "price_inr": "799",
       "materials": "100% organic cotton (sample claim; verify before real use)",
       "features": "Soft hand-feel; regular fit", "description": "A minimalist everyday T-shirt.",
       "available_colours": "Black; White; Sage Green",
       "advertising_restrictions": "Do not publish organic certification/material claims until verified."}
SHOES = {"product_id": "FTW-001", "product_name": "Trail Runner", "price_inr": "2,499",
         "materials": "Mesh upper; rubber outsole", "features": "Cushioned sole",
         "description": "A running shoe.", "available_colours": "Olive Green; Black",
         "advertising_restrictions": "Do not claim waterproofing."}
SUBSTANTIATED = {"product_id": "X-1", "product_name": "Hemp Bag", "price_inr": "999",
                 "materials": "Recycled polyester shell", "features": "", "description": "",
                 "available_colours": "Black", "advertising_restrictions": "Do not claim leather."}


def checks(h, c, t, product=SHOES, channel="Instagram feed"):
    return {v["check"] for v in C.check(h, c, t, product, channel)}


class Checker(unittest.TestCase):
    def test_guideline_ids_come_from_csv(self):
        ids = C.guideline_ids()
        self.assertEqual(ids["pricing"], C.rule_for("price"))
        self.assertTrue(all(v.startswith("BRAND-") for v in C.enforced_map().values()))

    # (a) prices
    def test_price_exact_ok(self):
        self.assertNotIn("price", checks("Run far", "Trail Runner at ₹2,499 for daily miles.", "Shop now"))
        self.assertNotIn("price", checks("Run far", "Only Rs. 2499 here.".replace("Only ", ""), "Shop now"))

    def test_price_wrong_amount(self):
        self.assertIn("price", checks("Run far", "Trail Runner for ₹1,999.", "Shop now"))

    def test_price_wrong_currency(self):
        self.assertIn("price", checks("Run far", "Trail Runner for $2499.", "Shop now"))

    def test_price_trailing_rupees(self):
        self.assertIn("price", checks("Run far", "Just 2000 rupees today.", "Shop now"))
        self.assertNotIn("price", checks("Run far", "Priced at 2499 rupees.", "Shop now"))

    def test_percent_material_is_not_a_price_or_discount(self):
        self.assertEqual(checks("Soft tee", "Made from 100% cotton for comfort.", "Shop now", TEE) & {"price", "discount"}, set())

    # (b) discounts etc.
    def test_discount_phrases(self):
        for text in ("Get 20% off today", "Flat 30% discount", "Our festive sale is on", "Buy one get one free",
                     "A special offer for you", "Save ₹200 now"):
            self.assertIn("discount", checks("Hello", text, "Shop now"), text)

    def test_discount_negative(self):
        self.assertNotIn("discount", checks("Light and quick", "Cushioned sole for daily runs.", "Shop now"))

    def test_coupon(self):
        self.assertIn("coupon", checks("Hi", "Use code RUN20 at checkout.", "Shop now"))
        self.assertNotIn("coupon", checks("Hi", "Cushioned sole for daily runs.", "Shop now"))

    def test_free_shipping(self):
        self.assertIn("free_shipping", checks("Hi", "Free shipping on every pair.", "Shop now"))
        self.assertNotIn("free_shipping", checks("Hi", "Shipping is calculated at checkout.", "Shop now"))

    def test_urgency_and_rule_by_channel(self):
        self.assertIn("urgency", checks("Hurry", "Only 3 left in stock.", "Shop now"))
        sms = C.check("Hurry", "Last chance to buy.", "Shop now", SHOES, "SMS")
        self.assertEqual([v["rule_id"] for v in sms if v["check"] == "urgency"][0], C.rule_for("urgency", "SMS"))
        other = C.check("Hurry", "Last chance to buy.", "Shop now", SHOES, "Email")
        self.assertEqual([v["rule_id"] for v in other if v["check"] == "urgency"][0], C.rule_for("urgency", "Email"))
        self.assertNotIn("urgency", checks("Easy", "A shoe for every day.", "Shop now"))

    # (c) environmental
    def test_environmental_flagged(self):
        for text in ("An eco-friendly choice.", "A sustainable pick.", "Planet-friendly design.", "Go green today."):
            self.assertIn("environmental", checks("Hello", text, "Shop now", SHOES), text)

    def test_colour_green_not_flagged(self):
        self.assertNotIn("environmental", checks("Hello", "Available in Olive Green and Black.", "Shop now", SHOES))
        self.assertNotIn("environmental", checks("Hello", "Pick the Sage Green one.", "Shop now", TEE))

    def test_environmental_forbidden_even_if_in_materials(self):
        self.assertIn("environmental", checks("Hello", "Made from organic cotton.", "Shop now", TEE))

    def test_environmental_substantiated_allowed(self):
        self.assertNotIn("environmental", checks("Hello", "A shell of recycled polyester.", "Shop now", SUBSTANTIATED))
        self.assertIn("environmental", checks("Hello", "A truly sustainable shell.", "Shop now", SUBSTANTIATED))

    def test_no_environmental_negative(self):
        self.assertNotIn("environmental", checks("Hello", "Cushioned sole for daily runs.", "Shop now"))

    # product-name carried claim
    def test_product_name_carries_claim(self):
        got = C.check("Meet the tee", "The Everyday Organic Cotton Tee fits everyone.", "Shop now", TEE, "Email")
        self.assertIn("product_name_claim", {v["check"] for v in got})
        self.assertNotIn("environmental", {v["check"] for v in got})

    def test_product_name_not_quoted_no_flag(self):
        got = C.check("Meet the tee", "A soft everyday cotton tee for students.", "Shop now", TEE, "Email")
        self.assertEqual({v["check"] for v in got} & {"product_name_claim", "environmental"}, set())

    def test_name_quoted_and_separate_claim(self):
        got = {v["check"] for v in C.check("Hi", "The Everyday Organic Cotton Tee is eco-friendly.", "Shop now", TEE, "")}
        self.assertEqual({"product_name_claim", "environmental"} & got, {"product_name_claim", "environmental"})

    # (d) CTA
    def test_cta_exactly_one(self):
        self.assertNotIn("cta", checks("H", "Body.", "Shop now"))
        self.assertIn("cta", checks("H", "Body.", ""))
        self.assertIn("cta", checks("H", "Body.", "Shop now or visit us"))
        self.assertIn("cta", checks("H", "Body.", "Buy now. Learn more."))
        self.assertEqual(C.count_ctas("Shop the tee"), 1)

    # (e) exclamation marks
    def test_exclamation(self):
        self.assertNotIn("exclamation", checks("Run!", "Daily miles.", "Shop now"))
        self.assertIn("exclamation", checks("Run!", "Daily miles!", "Shop now"))
        self.assertNotIn("exclamation", checks("Run", "Daily miles.", "Shop now"))

    # (f) SMS length
    def test_sms_length(self):
        long_copy = "word " * 40
        self.assertIn("sms_length", checks("H", long_copy, "Shop now", channel="SMS"))
        self.assertNotIn("sms_length", checks("H", long_copy, "Shop now", channel="Email"))
        self.assertNotIn("sms_length", checks("H", "Short.", "Shop now", channel="SMS"))

    def test_clean_output_has_no_violations(self):
        self.assertEqual(C.check("Run every day", "Trail Runner with a cushioned sole for daily runs, ₹2,499.",
                                 "Shop now", SHOES, "Email"), [])

    def test_output_shape(self):
        v = C.check("H", "Get 20% off.", "Shop now", SHOES, "Email")[0]
        self.assertEqual(set(v), {"rule_id", "check", "matched_text"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

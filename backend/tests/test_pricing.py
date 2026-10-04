"""Pricing engine unit tests — pure logic, no DB or network."""
from app.domain.pricing import LineItem, Promo, price_cart, promo_discount_for


def _cart():
    return [LineItem("p1", "Whey", 2499, 2), LineItem("p2", "Multivitamin", 699, 1)]


def test_subtotal_and_member_discount():
    q = price_cart(_cart(), member_discount_pct=0.15, tax_pct=0.0)
    assert q.subtotal == 2499 * 2 + 699            # 5697
    assert q.member_discount == round(5697 * 0.15)  # 855
    assert q.total == 5697 - 855                    # 4842
    assert q.tax == 0


def test_tax_applied_after_discounts():
    q = price_cart(_cart(), member_discount_pct=0.15, tax_pct=0.18)
    taxable = 5697 - round(5697 * 0.15)             # 4842
    assert q.taxable == taxable
    assert q.tax == round(taxable * 0.18)
    assert q.total == taxable + q.tax


def test_percent_promo():
    promo = Promo("WELCOME10", "percent", 10)
    q = price_cart(_cart(), member_discount_pct=0.15, tax_pct=0.0, promo=promo)
    after_member = 5697 - round(5697 * 0.15)        # 4842
    assert q.promo_discount == round(after_member * 0.10)
    assert q.promo_code == "WELCOME10"
    assert q.total == after_member - q.promo_discount


def test_flat_promo_with_min_subtotal_not_met():
    promo = Promo("MEROVA200", "flat", 200, min_subtotal=100000)
    disc, notes = promo_discount_for(4842, promo)
    assert disc == 0
    assert notes and "minimum" in notes[0].lower()


def test_promo_never_below_zero():
    promo = Promo("HUGE", "flat", 999999)
    disc, _ = promo_discount_for(500, promo)
    assert disc == 500  # capped at the amount, never negative


def test_inactive_promo_ignored():
    promo = Promo("OLD", "percent", 50, active=False)
    q = price_cart(_cart(), promo=promo)
    assert q.promo_discount == 0
    assert q.promo_code is None


def test_empty_cart():
    q = price_cart([], member_discount_pct=0.15, tax_pct=0.18)
    assert q.subtotal == 0 and q.total == 0 and q.tax == 0

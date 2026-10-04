"""Cart & checkout pricing — the single source of truth for money math.

All amounts are integer INR rupees (no floats for currency). A cart is priced in
one pass so the server, the checkout sheet, and the payment gateway always agree
on the same total. Promo codes are validated and applied here; tax is computed on
the post-discount amount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineItem:
    product_id: str
    name: str
    price: int          # unit price in INR rupees
    qty: int

    @property
    def line_total(self) -> int:
        return self.price * self.qty


@dataclass
class Promo:
    """A validated promo/discount code.

    kind = "percent" -> `value` is a whole percentage (e.g. 10 == 10% off)
    kind = "flat"    -> `value` is a flat INR amount off the subtotal
    """
    code: str
    kind: str
    value: int
    min_subtotal: int = 0
    active: bool = True


@dataclass
class Quote:
    items: list[LineItem]
    subtotal: int
    member_discount: int
    promo_code: Optional[str]
    promo_discount: int
    taxable: int
    tax: int
    total: int
    currency: str = "INR"
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "items": [
                {"product_id": i.product_id, "name": i.name, "price": i.price,
                 "qty": i.qty, "line_total": i.line_total}
                for i in self.items
            ],
            "subtotal": self.subtotal,
            "member_discount": self.member_discount,
            "promo_code": self.promo_code,
            "promo_discount": self.promo_discount,
            "taxable": self.taxable,
            "tax": self.tax,
            "total": self.total,
            "currency": self.currency,
            "notes": self.notes,
        }


def promo_discount_for(subtotal_after_member: int, promo: Optional[Promo]) -> tuple[int, list[str]]:
    """Return (discount_amount, notes). Invalid/inapplicable promos yield 0 + a note."""
    if promo is None:
        return 0, []
    notes: list[str] = []
    if not promo.active:
        return 0, [f"Promo {promo.code} is no longer active"]
    if subtotal_after_member < promo.min_subtotal:
        return 0, [f"Promo {promo.code} needs a minimum of ₹{promo.min_subtotal}"]
    if promo.kind == "percent":
        disc = round(subtotal_after_member * min(promo.value, 100) / 100)
    elif promo.kind == "flat":
        disc = min(promo.value, subtotal_after_member)
    else:
        return 0, [f"Promo {promo.code} has an unknown type"]
    # never let a promo drive the price below zero
    disc = max(0, min(disc, subtotal_after_member))
    return disc, notes


def price_cart(
    items: list[LineItem],
    *,
    member_discount_pct: float = 0.15,
    tax_pct: float = 0.0,
    promo: Optional[Promo] = None,
) -> Quote:
    """Price a cart end-to-end.

    Order of operations: subtotal -> member discount -> promo -> tax -> total.
    Tax is charged on the amount that remains after both discounts.
    """
    subtotal = sum(i.line_total for i in items)
    member_discount = round(subtotal * member_discount_pct)
    after_member = subtotal - member_discount
    promo_disc, notes = promo_discount_for(after_member, promo)
    taxable = max(0, after_member - promo_disc)
    tax = round(taxable * tax_pct)
    total = taxable + tax
    return Quote(
        items=items,
        subtotal=subtotal,
        member_discount=member_discount,
        promo_code=promo.code if (promo and promo_disc > 0) else None,
        promo_discount=promo_disc,
        taxable=taxable,
        tax=tax,
        total=total,
        notes=notes,
    )

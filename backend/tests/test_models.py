"""Request-model validation tests (password rules, phone, cart bounds)."""
import pytest
from pydantic import ValidationError

from app.models import CartAddIn, ChangePasswordIn, RegisterIn


def test_weak_password_rejected():
    with pytest.raises(ValidationError):
        RegisterIn(name="A", email="a@b.com", password="weak")


def test_strong_password_accepted():
    m = RegisterIn(name="Aaditya", email="a@b.com", password="Str0ng!Pass")
    assert m.email == "a@b.com"


def test_phone_normalised():
    m = RegisterIn(name="A", email="a@b.com", password="Str0ng!Pass", phone="+91 98765-43210")
    assert m.phone == "+919876543210"


def test_bad_phone_rejected():
    with pytest.raises(ValidationError):
        RegisterIn(name="A", email="a@b.com", password="Str0ng!Pass", phone="12")


def test_cart_qty_bounds():
    with pytest.raises(ValidationError):
        CartAddIn(product_id="p1", qty=0)
    with pytest.raises(ValidationError):
        CartAddIn(product_id="p1", qty=99)
    assert CartAddIn(product_id="p1", qty=3).qty == 3


def test_change_password_enforces_strength():
    with pytest.raises(ValidationError):
        ChangePasswordIn(current_password="x", new_password="weak")

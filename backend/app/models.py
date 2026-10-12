import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal, Optional, List

# ---- shared field rules ----
DATE_RX = r"^\d{4}-\d{2}-\d{2}$"           # YYYY-MM-DD
Day = Field(pattern=DATE_RX)
Password = Field(max_length=128)               # bcrypt only reads 72 bytes; stop huge inputs early


def clean_phone(v):
    """Accept +91 98765 43210 style input; store digits (and a leading +) only."""
    if v in (None, ""):
        return None
    digits = re.sub(r"[\s().-]", "", v)
    if not re.fullmatch(r"\+?\d{10,14}", digits):
        raise ValueError("Enter a valid mobile number (10-14 digits)")
    return digits

PW_RULES = [
    (r".{8,}", "at least 8 characters"),
    (r"[A-Z]", "an uppercase letter"),
    (r"[a-z]", "a lowercase letter"),
    (r"\d", "a number"),
    (r"[^A-Za-z0-9]", "a special character"),
]

def validate_password(p: str) -> str:
    missing = [msg for rx, msg in PW_RULES if not re.search(rx, p)]
    if missing:
        raise ValueError("Password needs " + ", ".join(missing))
    return p

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Password
    phone: Optional[str] = Field(default=None, max_length=24)

    @field_validator("password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)

    @field_validator("phone")
    @classmethod
    def phone_fmt(cls, v):
        return clean_phone(v)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Password

class GoogleIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)

class OTPRequestIn(BaseModel):
    email: EmailStr

class OTPVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\s*\d{6}\s*$")

    @field_validator("code")
    @classmethod
    def strip_code(cls, v):
        return v.strip()

class QuizIn(BaseModel):
    goal: Literal["lose_fat", "build_strength", "consistent"]
    activity: Literal["beginner", "some", "active"]
    days_per_week: Literal["3", "4-5", "6"]

class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    phone: Optional[str] = Field(default=None, max_length=24)
    dob: Optional[str] = Field(default=None, max_length=32)
    gender: Optional[str] = Field(default=None, max_length=32)
    height_cm: Optional[float] = Field(default=None, ge=50, le=260)

    @field_validator("phone")
    @classmethod
    def phone_fmt(cls, v):
        # the number gets WhatsApp messages from us, so it must at least look real
        return clean_phone(v) or ""

    @field_validator("name", "dob", "gender")
    @classmethod
    def no_markup(cls, v):
        if v is not None and re.search(r"[<>]", v):
            raise ValueError("can't contain < or >")
        return v.strip() if v is not None else v

class ExerciseLogIn(BaseModel):
    date: str = Day
    exercise: str = Field(min_length=1, max_length=120)
    done: bool
    weight_kg: Optional[float] = Field(default=None, ge=0, le=500)

class MealLogIn(BaseModel):
    date: str = Day
    slot: str = Field(min_length=1, max_length=32)   # breakfast/lunch/snack/dinner
    name: str = Field(min_length=1, max_length=120)
    kcal: int = Field(ge=0, le=5000)
    protein_g: int = Field(default=0, ge=0, le=1000)
    carbs_g: int = Field(default=0, ge=0, le=1000)
    fat_g: int = Field(default=0, ge=0, le=1000)

class WaterIn(BaseModel):
    date: str = Day
    glasses: int = Field(ge=0, le=20)

class WeightIn(BaseModel):
    date: str = Day
    weight_kg: float = Field(ge=20, le=400)

class CartItem(BaseModel):
    product_id: str = Field(max_length=64)
    qty: int = Field(ge=1, le=20)

class CheckoutIn(BaseModel):
    items: List[CartItem] = Field(max_length=50)
    promo_code: Optional[str] = Field(default=None, max_length=32)

class VerifyPaymentIn(BaseModel):
    order_id: str = Field(max_length=64)
    razorpay_order_id: str = Field(max_length=128)
    razorpay_payment_id: str = Field(max_length=128)
    razorpay_signature: str = Field(max_length=256)

class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

# what the app books: an intro call, or a class by its name ("class: HIIT Fat Burn")
BOOKING_KIND_RX = r"^(intro_call|class: [\w &'()+·-]{1,48})$"
# when: an ISO time from the class list, or a quick pick like "Tomorrow 6 PM"
BOOKING_WORD_RX = (r"^(Today|Tomorrow|Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
                   r"(1[0-2]|[1-9])(:[0-5]\d)? ?(AM|PM)$")

class BookingIn(BaseModel):
    slot: str = Field(min_length=1, max_length=40)
    kind: str = Field(default="intro_call", pattern=BOOKING_KIND_RX)

    @field_validator("slot")
    @classmethod
    def slot_fmt(cls, v):
        v = v.strip()
        if re.fullmatch(BOOKING_WORD_RX, v):
            return v
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Pick a time from the list")
        return v

class AssignPlanIn(BaseModel):
    client_id: str = Field(max_length=64)
    workout_title: str = Field(min_length=1, max_length=120)
    exercises: List[dict] = Field(max_length=40)        # [{name, detail}]
    daily_kcal: int = Field(ge=800, le=6000)
    meals: List[dict] = Field(max_length=12)            # [{slot,name,kcal,protein_g,carbs_g,fat_g}]

class BroadcastIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    segment: str = Field(default="all", max_length=20)


# ============ v2 models ============

class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=2048)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    password: str = Password

    @field_validator("password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)


class ChangePasswordIn(BaseModel):
    current_password: str = Password
    new_password: str = Password

    @field_validator("new_password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)


class AppleIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)
    name: Optional[str] = Field(default=None, max_length=80)   # Apple only sends the name on first consent


class PreferencesIn(BaseModel):
    units: Optional[str] = None                 # metric | imperial
    theme: Optional[str] = None                 # dark | light | system
    notif_workouts: Optional[bool] = None
    notif_meals: Optional[bool] = None
    notif_water: Optional[bool] = None
    notif_promotions: Optional[bool] = None
    water_goal: Optional[int] = Field(default=None, ge=1, le=30)
    notif_push: Optional[bool] = None
    notif_whatsapp: Optional[bool] = None
    notif_email: Optional[bool] = None


class DeleteAccountIn(BaseModel):
    password: Optional[str] = Field(default=None, max_length=128)  # required for password accounts
    confirm: str = Field(max_length=16)  # must equal "DELETE"


# --- cart ---
class CartAddIn(BaseModel):
    product_id: str
    qty: int = Field(default=1, ge=1, le=20)


class CartQtyIn(BaseModel):
    product_id: str
    qty: int = Field(ge=0, le=20)       # 0 removes the line


class PromoIn(BaseModel):
    code: str = Field(min_length=2, max_length=32)


# --- subscriptions ---
class SubscribeIn(BaseModel):
    plan_code: str                       # premium_monthly | premium_annual
    start_trial: bool = False


class VerifySubPaymentIn(BaseModel):
    subscription_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# --- goals ---
class GoalCompleteIn(BaseModel):
    goal_id: str
    period: str = "daily"                # daily | weekly | monthly


# --- progress ---
class MeasurementIn(BaseModel):
    date: str = Day
    waist_cm: Optional[float] = Field(default=None, ge=0, le=300)
    chest_cm: Optional[float] = Field(default=None, ge=0, le=300)
    hips_cm: Optional[float] = Field(default=None, ge=0, le=300)
    arm_cm: Optional[float] = Field(default=None, ge=0, le=150)
    thigh_cm: Optional[float] = Field(default=None, ge=0, le=200)
    body_fat_pct: Optional[float] = Field(default=None, ge=0, le=80)


# --- notifications / push ---
class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    platform: Literal["web", "ios", "android"] = "web"


# --- admin ---
class AdminNotifyIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=400)
    segment: str = "all"                # all | premium | free
    user_id: Optional[str] = None       # target a single user instead of a segment


class AdminUserPatch(BaseModel):
    banned: Optional[bool] = None
    role: Optional[Literal["client", "coach", "admin"]] = None
    daily_kcal: Optional[int] = Field(default=None, ge=800, le=6000)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: int = Field(ge=0, le=1_000_000)
    mrp: int = Field(ge=0, le=1_000_000)
    cat: str = Field(min_length=1, max_length=40)
    badge: Optional[str] = Field(default=None, max_length=30)
    note: Optional[str] = Field(default=None, max_length=200)

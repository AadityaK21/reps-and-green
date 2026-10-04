import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List

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
    password: str
    phone: Optional[str] = None

    @field_validator("password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)

    @field_validator("phone")
    @classmethod
    def phone_fmt(cls, v):
        if v in (None, ""):
            return None
        digits = re.sub(r"[\s-]", "", v)
        if not re.fullmatch(r"\+?\d{10,14}", digits):
            raise ValueError("Enter a valid mobile number (10-14 digits)")
        return digits

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class GoogleIn(BaseModel):
    id_token: str

class OTPRequestIn(BaseModel):
    email: EmailStr

class OTPVerifyIn(BaseModel):
    email: EmailStr
    code: str

class QuizIn(BaseModel):
    goal: str            # lose_fat | build_strength | consistent
    activity: str        # beginner | some | active
    days_per_week: str   # 3 | 4-5 | 6

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    height_cm: Optional[float] = None

class ExerciseLogIn(BaseModel):
    date: str            # YYYY-MM-DD
    exercise: str
    done: bool
    weight_kg: Optional[float] = None

class MealLogIn(BaseModel):
    date: str
    slot: str            # breakfast/lunch/snack/dinner
    name: str
    kcal: int
    protein_g: int = 0
    carbs_g: int = 0
    fat_g: int = 0

class WaterIn(BaseModel):
    date: str
    glasses: int = Field(ge=0, le=20)

class WeightIn(BaseModel):
    date: str
    weight_kg: float

class CartItem(BaseModel):
    product_id: str
    qty: int = Field(ge=1, le=20)

class CheckoutIn(BaseModel):
    items: List[CartItem]
    promo_code: Optional[str] = None

class VerifyPaymentIn(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

class BookingIn(BaseModel):
    slot: str            # ISO datetime string
    kind: str = "intro_call"

class AssignPlanIn(BaseModel):
    client_id: str
    workout_title: str
    exercises: List[dict]        # [{name, detail}]
    daily_kcal: int
    meals: List[dict]            # [{slot,name,kcal,protein_g,carbs_g,fat_g}]

class BroadcastIn(BaseModel):
    text: str
    segment: str = "all"


# ============ v2 models ============

class RefreshIn(BaseModel):
    refresh_token: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pw_strong(cls, v):
        return validate_password(v)


class AppleIn(BaseModel):
    id_token: str
    name: Optional[str] = None          # Apple only sends the name on first consent


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
    password: Optional[str] = None      # required for password accounts
    confirm: str                        # must equal "DELETE"


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
    date: str
    waist_cm: Optional[float] = None
    chest_cm: Optional[float] = None
    hips_cm: Optional[float] = None
    arm_cm: Optional[float] = None
    thigh_cm: Optional[float] = None
    body_fat_pct: Optional[float] = None


# --- notifications / push ---
class DeviceTokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    platform: str = "web"               # web | ios | android


# --- admin ---
class AdminNotifyIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=400)
    segment: str = "all"                # all | premium | free
    user_id: Optional[str] = None       # target a single user instead of a segment


class AdminUserPatch(BaseModel):
    banned: Optional[bool] = None
    role: Optional[str] = None          # client | coach | admin
    daily_kcal: Optional[int] = None


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: int = Field(ge=0)
    mrp: int = Field(ge=0)
    cat: str
    badge: Optional[str] = None
    note: Optional[str] = None

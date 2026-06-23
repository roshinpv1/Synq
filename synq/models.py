import datetime
import re
from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, field_validator



class CardProduct(str, Enum):
    DEBIT = "Debit Card"
    REWARDS_CREDIT = "Rewards Credit Card"
    PREMIUM_CREDIT = "Premium Credit Card"


class Segment(str, Enum):
    # Behavioral
    DINERS = "Frequent Diners"
    COFFEE_BUYERS = "Coffee Buyers"
    TRAVELERS = "Travelers"
    # Spend
    HIGH_SPENDERS = "High Spenders"
    COMPETITOR_SPENDERS = "Competitor Spenders"
    # Location
    LOCAL = "Local Radius"
    # Product
    CREDIT_HOLDERS = "Credit Card Holders"
    REWARDS_CUSTOMERS = "Rewards Customers"


class OfferType(str, Enum):
    CASHBACK_PERCENT = "Cashback Percentage"
    CASHBACK_FLAT = "Cashback Flat Amount"
    POINTS_MULTIPLIER = "Points Multiplier"


class CampaignStatus(str, Enum):
    DRAFT = "Draft"
    PENDING_COMPLIANCE = "Pending Compliance Review"
    ACTIVE = "Active"
    REJECTED = "Rejected"
    COMPLETED = "Completed"


class Category(str, Enum):
    DINING = "Dining"
    COFFEE = "Coffee"
    TRAVEL = "Travel"
    RETAIL = "Retail"
    FITNESS = "Fitness"
    GROCERY = "Grocery"
    ENTERTAINMENT = "Entertainment"
    ELECTRONICS = "Electronics"
    APPAREL = "Apparel"
    GAS_AUTO = "Gas & Automotive"
    BEAUTY_WELLNESS = "Beauty & Wellness"


class ConsentPreferences(BaseModel):
    personalization: bool = True
    notifications: bool = True
    location: bool = True


class CustomerTransaction(BaseModel):
    transaction_id: str
    merchant_name: str
    category: Category
    amount: float
    timestamp: datetime.datetime

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Transaction amount must be positive")
        return v



class CustomerRewards(BaseModel):
    accumulated_cashback: float = 0.0
    redemption_count: int = 0
    history: List[Dict[str, Any]] = []  # List of dicts representing rewards events


# Customer 360 Profile Model
class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    products: List[CardProduct] = []
    transactions: List[CustomerTransaction] = []
    rewards: CustomerRewards = CustomerRewards()
    affinity_scores: Dict[Category, float] = {
        Category.DINING: 5.0,
        Category.COFFEE: 5.0,
        Category.TRAVEL: 5.0,
        Category.RETAIL: 5.0,
        Category.FITNESS: 5.0,
        Category.GROCERY: 5.0,
        Category.ENTERTAINMENT: 5.0,
        Category.ELECTRONICS: 5.0,
        Category.APPAREL: 5.0,
        Category.GAS_AUTO: 5.0,
        Category.BEAUTY_WELLNESS: 5.0
    }
    preferences: ConsentPreferences = ConsentPreferences()
    age: Optional[int] = None
    gender: Optional[str] = None
    income_bracket: Optional[str] = None
    home_latitude: Optional[float] = None
    home_longitude: Optional[float] = None

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Invalid email format")
        return v


# Merchant Model
class Merchant(BaseModel):
    merchant_id: str
    name: str
    category: Category
    onboarded: bool = False
    verification_status: str = "Pending"  # Pending, Verified, Failed
    address: str
    latitude: float
    longitude: float

    @field_validator('latitude')
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator('longitude')
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v



# Campaign Model
class Campaign(BaseModel):
    campaign_id: str
    merchant_id: str
    merchant_name: str
    name: str
    category: Category
    offer_type: OfferType
    offer_value: float  # e.g., 10.0 for 10% or $10.0
    min_spend: float = 0.0
    budget: float
    remaining_budget: float
    duration_days: int
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    audience_segments: List[Segment] = []
    marketing_copy: str = ""
    legal_disclosure: str = ""
    status: CampaignStatus = CampaignStatus.DRAFT
    compliance_feedback: Optional[str] = None
    
    # Performance metrics
    impressions: int = 0
    activations: int = 0
    redemptions: int = 0
    total_spend_driven: float = 0.0
    total_cashback_paid: float = 0.0

    @field_validator('budget')
    @classmethod
    def validate_budget(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Budget must be a positive number")
        return v

    @field_validator('offer_value')
    @classmethod
    def validate_offer_value(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Offer value must be a positive number")
        return v

    @field_validator('min_spend')
    @classmethod
    def validate_min_spend(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Minimum spend cannot be negative")
        return v

    @field_validator('duration_days')
    @classmethod
    def validate_duration_days(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Duration days must be a positive integer")
        return v

    @property
    def roi(self) -> float:
        if self.total_cashback_paid == 0:
            return 0.0
        # ROI is driven spend divided by merchant cost (cashback paid)
        return round((self.total_spend_driven / self.total_cashback_paid), 2)



# Active Offer state (when a customer activates an offer)
class ActiveOffer(BaseModel):
    customer_id: str
    campaign_id: str
    activated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


# Redemption Event Model
class Redemption(BaseModel):
    redemption_id: str
    customer_id: str
    campaign_id: str
    merchant_name: str
    transaction_id: str
    transaction_amount: float
    cashback_amount: float
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)


# Settlement & Billing Record Model
class BillingRecord(BaseModel):
    record_id: str
    redemption_id: str
    merchant_id: str
    merchant_name: str
    cashback_charge: float  # Charged back to merchant to cover cashback
    bank_fee: float        # Bank fee revenue (e.g. 15% of the offer value or 2% of transaction)
    total_charged: float   # cashback_charge + bank_fee
    settled: bool = False
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)


# User Auth Models
class User(BaseModel):
    username: str
    role: str
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: str = Field(..., pattern="^(admin_compliance|merchant|consumer)$")
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None


class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


import os
import json
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager

from synq.db_models import (
    Base, DBMerchant, DBCustomer, DBCustomerTransaction, 
    DBCampaign, DBRedemption, DBBillingRecord, DBActiveOffer, DBAgentLog, DBUser
)
from synq.models import (
    Merchant, Customer, CustomerTransaction, CustomerRewards,
    Campaign, Redemption, BillingRecord, Category, CardProduct,
    ConsentPreferences, OfferType, CampaignStatus, Segment, User
)


# Resolve Database URL (support Postgres or generic override, fallback to home directory sqlite)
_DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".synq", "synq.db")
os.makedirs(os.path.dirname(_DEFAULT_DB_PATH), exist_ok=True)

DATABASE_URL = os.environ.get("SYNQ_DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")

# For SQLite, enable check_same_thread=False since FastAPI handles threading
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = scoped_session(session_factory)

def init_db():
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# -----------------------------------------------------------------------------
# CONVERSION HELPERS (Pydantic <-> ORM)
# -----------------------------------------------------------------------------

def to_db_merchant(m: Merchant) -> DBMerchant:
    return DBMerchant(
        merchant_id=m.merchant_id,
        name=m.name,
        category=m.category.value,
        onboarded=m.onboarded,
        verification_status=m.verification_status,
        address=m.address,
        latitude=m.latitude,
        longitude=m.longitude
    )

def from_db_merchant(db_m: DBMerchant) -> Merchant:
    return Merchant(
        merchant_id=db_m.merchant_id,
        name=db_m.name,
        category=Category(db_m.category),
        onboarded=db_m.onboarded,
        verification_status=db_m.verification_status,
        address=db_m.address,
        latitude=db_m.latitude,
        longitude=db_m.longitude
    )

def to_db_customer(c: Customer) -> DBCustomer:
    # Convert preferences to bools
    # Convert lists/dicts to json
    products_json = json.dumps([p.value for p in c.products])
    history_json = json.dumps(c.rewards.history)
    affinity_json = json.dumps({cat.value: score for cat, score in c.affinity_scores.items()})
    
    return DBCustomer(
        customer_id=c.customer_id,
        name=c.name,
        email=c.email,
        products=products_json,
        accumulated_cashback=c.rewards.accumulated_cashback,
        redemption_count=c.rewards.redemption_count,
        rewards_history=history_json,
        affinity_scores=affinity_json,
        personalization=c.preferences.personalization,
        notifications=c.preferences.notifications,
        location=c.preferences.location,
        age=c.age,
        gender=c.gender,
        income_bracket=c.income_bracket,
        home_latitude=c.home_latitude,
        home_longitude=c.home_longitude
    )

def from_db_customer(db_c: DBCustomer) -> Customer:
    # Deserialize list/dicts
    try:
        products = [CardProduct(p) for p in json.loads(db_c.products or "[]")]
    except Exception:
        products = []
        
    try:
        history = json.loads(db_c.rewards_history or "[]")
    except Exception:
        history = []
        
    try:
        affinity_raw = json.loads(db_c.affinity_scores or "{}")
        affinity = {Category(k): v for k, v in affinity_raw.items()}
    except Exception:
        affinity = {cat: 5.0 for cat in Category}

    # Load transactions
    tx_list = []
    for tx in db_c.transactions:
        tx_list.append(CustomerTransaction(
            transaction_id=tx.transaction_id,
            merchant_name=tx.merchant_name,
            category=Category(tx.category),
            amount=tx.amount,
            timestamp=tx.timestamp
        ))
    # Sort transactions descending by timestamp
    tx_list.sort(key=lambda x: x.timestamp, reverse=True)

    return Customer(
        customer_id=db_c.customer_id,
        name=db_c.name,
        email=db_c.email,
        products=products,
        transactions=tx_list,
        rewards=CustomerRewards(
            accumulated_cashback=db_c.accumulated_cashback,
            redemption_count=db_c.redemption_count,
            history=history
        ),
        affinity_scores=affinity,
        preferences=ConsentPreferences(
            personalization=db_c.personalization,
            notifications=db_c.notifications,
            location=db_c.location
        ),
        age=db_c.age,
        gender=db_c.gender,
        income_bracket=db_c.income_bracket,
        home_latitude=db_c.home_latitude,
        home_longitude=db_c.home_longitude
    )

def to_db_transaction(tx: CustomerTransaction, customer_id: str) -> DBCustomerTransaction:
    return DBCustomerTransaction(
        transaction_id=tx.transaction_id,
        customer_id=customer_id,
        merchant_name=tx.merchant_name,
        category=tx.category.value,
        amount=tx.amount,
        timestamp=tx.timestamp
    )

def to_db_campaign(c: Campaign) -> DBCampaign:
    return DBCampaign(
        campaign_id=c.campaign_id,
        merchant_id=c.merchant_id,
        merchant_name=c.merchant_name,
        name=c.name,
        category=c.category.value,
        offer_type=c.offer_type.value,
        offer_value=c.offer_value,
        min_spend=c.min_spend,
        budget=c.budget,
        remaining_budget=c.remaining_budget,
        duration_days=c.duration_days,
        created_at=c.created_at,
        audience_segments=json.dumps([s.value for s in c.audience_segments]),
        marketing_copy=c.marketing_copy,
        legal_disclosure=c.legal_disclosure,
        status=c.status.value,
        compliance_feedback=c.compliance_feedback,
        impressions=c.impressions,
        activations=c.activations,
        redemptions=c.redemptions,
        total_spend_driven=c.total_spend_driven,
        total_cashback_paid=c.total_cashback_paid
    )

def from_db_campaign(db_c: DBCampaign) -> Campaign:
    try:
        segments = [Segment(s) for s in json.loads(db_c.audience_segments or "[]")]
    except Exception:
        segments = []

    return Campaign(
        campaign_id=db_c.campaign_id,
        merchant_id=db_c.merchant_id,
        merchant_name=db_c.merchant_name,
        name=db_c.name,
        category=Category(db_c.category),
        offer_type=OfferType(db_c.offer_type),
        offer_value=db_c.offer_value,
        min_spend=db_c.min_spend,
        budget=db_c.budget,
        remaining_budget=db_c.remaining_budget,
        duration_days=db_c.duration_days,
        created_at=db_c.created_at,
        audience_segments=segments,
        marketing_copy=db_c.marketing_copy,
        legal_disclosure=db_c.legal_disclosure,
        status=CampaignStatus(db_c.status),
        compliance_feedback=db_c.compliance_feedback,
        impressions=db_c.impressions,
        activations=db_c.activations,
        redemptions=db_c.redemptions,
        total_spend_driven=db_c.total_spend_driven,
        total_cashback_paid=db_c.total_cashback_paid
    )

def to_db_redemption(r: Redemption) -> DBRedemption:
    return DBRedemption(
        redemption_id=r.redemption_id,
        customer_id=r.customer_id,
        campaign_id=r.campaign_id,
        merchant_name=r.merchant_name,
        transaction_id=r.transaction_id,
        transaction_amount=r.transaction_amount,
        cashback_amount=r.cashback_amount,
        timestamp=r.timestamp
    )

def from_db_redemption(db_r: DBRedemption) -> Redemption:
    return Redemption(
        redemption_id=db_r.redemption_id,
        customer_id=db_r.customer_id,
        campaign_id=db_r.campaign_id,
        merchant_name=db_r.merchant_name,
        transaction_id=db_r.transaction_id,
        transaction_amount=db_r.transaction_amount,
        cashback_amount=db_r.cashback_amount,
        timestamp=db_r.timestamp
    )

def to_db_billing(b: BillingRecord) -> DBBillingRecord:
    return DBBillingRecord(
        record_id=b.record_id,
        redemption_id=b.redemption_id,
        merchant_id=b.merchant_id,
        merchant_name=b.merchant_name,
        cashback_charge=b.cashback_charge,
        bank_fee=b.bank_fee,
        total_charged=b.total_charged,
        settled=b.settled,
        timestamp=b.timestamp
    )

def from_db_billing(db_b: DBBillingRecord) -> BillingRecord:
    return BillingRecord(
        record_id=db_b.record_id,
        redemption_id=db_b.redemption_id,
        merchant_id=db_b.merchant_id,
        merchant_name=db_b.merchant_name,
        cashback_charge=db_b.cashback_charge,
        bank_fee=db_b.bank_fee,
        total_charged=db_b.total_charged,
        settled=db_b.settled,
        timestamp=db_b.timestamp
    )

def from_db_user(db_user: DBUser) -> User:
    return User(
        username=db_user.username,
        role=db_user.role,
        customer_id=db_user.customer_id,
        merchant_id=db_user.merchant_id
    )


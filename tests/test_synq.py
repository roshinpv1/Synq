import pytest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from synq.db_models import Base, DBCustomer, DBCampaign, DBMerchant
from synq.database import to_db_customer, to_db_campaign, to_db_merchant
from synq.models import (
    Customer, CustomerTransaction, Campaign, CampaignStatus, OfferType, 
    Category, CardProduct, Segment, CustomerRewards
)
from synq.engine import (
    TransactionMatchingEngine, CashbackProcessor, SettlementEngine
)
from synq.agents import ComplianceAgent, CampaignAgent

@pytest.fixture
def db_session():
    # Set up an ephemeral in-memory SQLite database for fast unit testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_merchant_onboarding_and_campaign_creation():
    # Test compliance agent audit on compliant text
    review = ComplianceAgent.review_campaign(
        campaign_name="Healthy Greens Boost",
        merchant_category="Fitness",
        marketing_copy="Get 10% cashback on organic protein shakes at GymLife!",
        legal_disclosure="Valid on debit transactions. Min spend $10. Max reward $5."
    )
    
    assert review.is_compliant is True
    assert len(review.flagged_reasons) == 0

    # Test compliance agent audit on restricted alcohol text
    review_bad = ComplianceAgent.review_campaign(
        campaign_name="Nightlife Beer Bonanza",
        merchant_category="Dining",
        marketing_copy="Get unlimited cashback on beers and cocktails!",
        legal_disclosure="Spend anything."
    )

    assert review_bad.is_compliant is False
    assert any("restricted" in r.lower() or "alcohol" in r.lower() for r in review_bad.flagged_reasons)


def test_transaction_matching_engine(db_session):
    # 1. Setup entities in DB
    db_merchant = DBMerchant(
        merchant_id="m_starbucks",
        name="Starbucks Coffee",
        category="Coffee",
        onboarded=True,
        verification_status="Verified",
        address="123 Main St",
        latitude=37.0,
        longitude=-122.0
    )
    db_session.add(db_merchant)

    db_customer = DBCustomer(
        customer_id="c_test",
        name="John Doe",
        email="john@doe.com",
        products='["Debit Card"]',
        accumulated_cashback=0.0,
        redemption_count=0,
        rewards_history='[]',
        affinity_scores='{"Coffee": 8.0}',
        personalization=True,
        notifications=True,
        location=True
    )
    db_session.add(db_customer)

    db_campaign = DBCampaign(
        campaign_id="camp_starbucks_test",
        merchant_id="m_starbucks",
        merchant_name="Starbucks Coffee",
        name="Coffee Special",
        offer_type="Cashback Percentage",
        offer_value=10.0,
        min_spend=5.0,
        budget=100.0,
        remaining_budget=100.0,
        duration_days=30,
        status="Active",
        category="Coffee",
        audience_segments='["Coffee Buyers"]'
    )
    db_session.add(db_campaign)
    db_session.commit()

    engine = TransactionMatchingEngine()

    # 2. Simulate Swiping before activating
    tx_unmatched = CustomerTransaction(
        transaction_id="tx_1",
        merchant_name="Starbucks Coffee",
        category=Category.COFFEE,
        amount=6.0,
        timestamp=datetime.datetime.now()
    )
    
    match = engine.match_transaction("c_test", tx_unmatched, db_session)
    assert match is None  # Should not match because not activated

    # 3. Activate offer
    engine.activate_offer("c_test", "camp_starbucks_test", db_session)
    db_session.commit()
    assert "camp_starbucks_test" in engine.get_activated_campaign_ids("c_test", db_session)

    # 4. Simulate Swiping under min spend ($5)
    tx_low = CustomerTransaction(
        transaction_id="tx_2",
        merchant_name="Starbucks Coffee",
        category=Category.COFFEE,
        amount=3.00,
        timestamp=datetime.datetime.now()
    )
    match = engine.match_transaction("c_test", tx_low, db_session)
    assert match is None  # Should not match under min spend

    # 5. Simulate Successful Swiping
    tx_good = CustomerTransaction(
        transaction_id="tx_3",
        merchant_name="Starbucks Coffee",
        category=Category.COFFEE,
        amount=10.00,
        timestamp=datetime.datetime.now()
    )
    match = engine.match_transaction("c_test", tx_good, db_session)
    assert match is not None
    matched_camp, cashback = match
    assert matched_camp.campaign_id == "camp_starbucks_test"
    assert cashback == 1.00  # 10% of $10.00


def test_cashback_and_settlement_ledger(db_session):
    # 1. Setup DB state
    db_merchant = DBMerchant(
        merchant_id="m_target",
        name="Target Store",
        category="Retail",
        onboarded=True,
        verification_status="Verified",
        address="456 Oak St",
        latitude=37.1,
        longitude=-122.1
    )
    db_session.add(db_merchant)

    db_customer = DBCustomer(
        customer_id="c_test",
        name="John Doe",
        email="john@doe.com",
        products='["Debit Card"]',
        accumulated_cashback=0.0,
        redemption_count=0,
        rewards_history='[]',
        affinity_scores='{"Retail": 5.0}',
        personalization=True,
        notifications=True,
        location=True
    )
    db_session.add(db_customer)

    db_campaign = DBCampaign(
        campaign_id="camp_target_test",
        merchant_id="m_target",
        merchant_name="Target Store",
        name="Target Deal",
        offer_type="Cashback Flat Amount",
        offer_value=5.0,
        min_spend=20.0,
        budget=100.0,
        remaining_budget=100.0,
        duration_days=30,
        status="Active",
        category="Retail",
        audience_segments='["Rewards Customers"]'
    )
    db_session.add(db_campaign)
    db_session.commit()

    # Simulate transaction
    tx = CustomerTransaction(
        transaction_id="tx_4",
        merchant_name="Target Store",
        category=Category.RETAIL,
        amount=30.00,
        timestamp=datetime.datetime.now()
    )

    cashback_amount = 5.00

    # Process Redemption
    redemption = CashbackProcessor.process_redemption(
        session=db_session,
        customer_id="c_test",
        transaction=tx,
        campaign_id="camp_target_test",
        cashback_amount=cashback_amount
    )
    db_session.commit()

    assert redemption.cashback_amount == 5.00
    
    # Verify Customer DB update
    updated_customer = db_session.query(DBCustomer).filter_by(customer_id="c_test").first()
    assert updated_customer.accumulated_cashback == 5.00
    assert updated_customer.redemption_count == 1
    
    # Verify Campaign DB update
    updated_campaign = db_session.query(DBCampaign).filter_by(campaign_id="camp_target_test").first()
    assert updated_campaign.remaining_budget == 95.00
    assert updated_campaign.redemptions == 1
    assert updated_campaign.total_spend_driven == 30.00

    # Process Settlement
    billing = SettlementEngine.calculate_merchant_fee(db_session, redemption, "camp_target_test")
    db_session.commit()

    assert billing.cashback_charge == 5.00
    # Bank fee: flat $0.25 + 10% of cashback ($0.50) = $0.75
    assert billing.bank_fee == 0.75
    assert billing.total_charged == 5.75
    assert billing.settled is False

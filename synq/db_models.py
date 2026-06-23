import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class DBActiveOffer(Base):
    __tablename__ = 'active_offers'
    
    customer_id = Column(String(50), primary_key=True)
    campaign_id = Column(String(50), primary_key=True)
    activated_at = Column(DateTime, default=datetime.datetime.now)

class DBMerchant(Base):
    __tablename__ = 'merchants'
    
    merchant_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    onboarded = Column(Boolean, default=False)
    verification_status = Column(String(50), default="Pending")
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    campaigns = relationship("DBCampaign", back_populates="merchant", cascade="all, delete-orphan")

class DBCustomer(Base):
    __tablename__ = 'customers'
    
    customer_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    products = Column(Text, default="[]")  # JSON string list
    accumulated_cashback = Column(Float, default=0.0)
    redemption_count = Column(Integer, default=0)
    rewards_history = Column(Text, default="[]")  # JSON string list
    affinity_scores = Column(Text, default="{}")  # JSON string dict
    personalization = Column(Boolean, default=True)
    notifications = Column(Boolean, default=True)
    location = Column(Boolean, default=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    income_bracket = Column(String(50), nullable=True)
    home_latitude = Column(Float, nullable=True)
    home_longitude = Column(Float, nullable=True)

    transactions = relationship("DBCustomerTransaction", back_populates="customer", cascade="all, delete-orphan")

class DBCustomerTransaction(Base):
    __tablename__ = 'customer_transactions'
    
    transaction_id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), ForeignKey('customers.customer_id', ondelete='CASCADE'), nullable=False)
    merchant_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.now)

    customer = relationship("DBCustomer", back_populates="transactions")

class DBCampaign(Base):
    __tablename__ = 'campaigns'
    
    campaign_id = Column(String(50), primary_key=True)
    merchant_id = Column(String(50), ForeignKey('merchants.merchant_id', ondelete='CASCADE'), nullable=False)
    merchant_name = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    offer_type = Column(String(50), nullable=False)
    offer_value = Column(Float, nullable=False)
    min_spend = Column(Float, default=0.0)
    budget = Column(Float, nullable=False)
    remaining_budget = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    audience_segments = Column(Text, default="[]")  # JSON string list
    marketing_copy = Column(Text, default="")
    legal_disclosure = Column(Text, default="")
    status = Column(String(50), default="Draft")
    compliance_feedback = Column(Text, nullable=True)
    
    impressions = Column(Integer, default=0)
    activations = Column(Integer, default=0)
    redemptions = Column(Integer, default=0)
    total_spend_driven = Column(Float, default=0.0)
    total_cashback_paid = Column(Float, default=0.0)

    merchant = relationship("DBMerchant", back_populates="campaigns")

class DBRedemption(Base):
    __tablename__ = 'redemptions'
    
    redemption_id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), ForeignKey('customers.customer_id', ondelete='CASCADE'), nullable=False)
    campaign_id = Column(String(50), ForeignKey('campaigns.campaign_id', ondelete='CASCADE'), nullable=False)
    merchant_name = Column(String(100), nullable=False)
    transaction_id = Column(String(50), ForeignKey('customer_transactions.transaction_id', ondelete='CASCADE'), nullable=False)
    transaction_amount = Column(Float, nullable=False)
    cashback_amount = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.now)

class DBBillingRecord(Base):
    __tablename__ = 'billing_records'
    
    record_id = Column(String(50), primary_key=True)
    redemption_id = Column(String(50), ForeignKey('redemptions.redemption_id', ondelete='CASCADE'), nullable=False)
    merchant_id = Column(String(50), ForeignKey('merchants.merchant_id', ondelete='CASCADE'), nullable=False)
    merchant_name = Column(String(100), nullable=False)
    cashback_charge = Column(Float, nullable=False)
    bank_fee = Column(Float, nullable=False)
    total_charged = Column(Float, nullable=False)
    settled = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.datetime.now)

class DBAgentLog(Base):
    __tablename__ = 'agent_logs'
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(50), nullable=False)
    agent = Column(String(100), nullable=False)
    input_data = Column(Text, nullable=False)
    output_data = Column(Text, nullable=False)
    trace_id = Column(String(50), nullable=True)

class DBUser(Base):
    __tablename__ = 'users'
    
    username = Column(String(50), primary_key=True)
    hashed_password = Column(String(128), nullable=False)
    salt = Column(String(64), nullable=False)
    role = Column(String(50), nullable=False)
    customer_id = Column(String(50), ForeignKey('customers.customer_id', ondelete='SET NULL'), nullable=True)
    merchant_id = Column(String(50), ForeignKey('merchants.merchant_id', ondelete='SET NULL'), nullable=True)


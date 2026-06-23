import os
import uuid
import datetime
import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Body, Header, Depends, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import Synq package items
from synq.models import (
    Customer, CustomerTransaction, CustomerRewards, Category, CardProduct,
    ConsentPreferences, Merchant, Campaign, CampaignStatus, OfferType, Segment,
    Redemption, BillingRecord, User, UserRegisterRequest, UserLoginResponse
)
from synq.engine import (
    TransactionMatchingEngine, CashbackProcessor, SettlementEngine
)
from synq.agents import (
    CampaignAgent, ComplianceAgent, AffinityAgent, RankingAgent
)

# Import DB Layer
from synq.database import (
    init_db, get_db_session,
    to_db_merchant, from_db_merchant,
    to_db_customer, from_db_customer,
    to_db_campaign, from_db_campaign,
    to_db_redemption, from_db_redemption,
    to_db_billing, from_db_billing,
    to_db_transaction, from_db_user
)
from synq.db_models import (
    DBMerchant, DBCustomer, DBCustomerTransaction,
    DBCampaign, DBRedemption, DBBillingRecord, DBActiveOffer, DBAgentLog, DBUser
)

# Import Auth
from synq.auth import (
    create_access_token, get_current_user_payload, get_password_hash, verify_password
)


# Observability Imports
import logging
from synq.logging_config import setup_logging, request_trace_id
from fastapi import Request

app = FastAPI(
    title="Synq Commerce Network API",
    description="Backend API for Banking-Powered Commerce Intelligence Network",
    version="1.0.0"
)

# Enable CORS for local testing (read allowed origins from env for security in prod)
allowed_origins = os.environ.get("SYNQ_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trace ID Middleware
@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex
    token = request_trace_id.set(trace_id)
    try:
        logging.info(f"Request started: {request.method} {request.url.path}")
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        logging.info(f"Request finished: {request.method} {request.url.path} - Status: {response.status_code}")
        return response
    finally:
        request_trace_id.reset(token)

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = request_trace_id.get(None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "trace_id": trace_id}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = request_trace_id.get(None)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "trace_id": trace_id}
    )

from pydantic import ValidationError

@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    trace_id = request_trace_id.get(None)
    sanitized_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
            err_copy["ctx"] = {k: str(v) for k, v in err_copy["ctx"].items()}
        sanitized_errors.append(err_copy)
    return JSONResponse(
        status_code=400,
        content={"detail": sanitized_errors, "trace_id": trace_id}
    )



@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    trace_id = request_trace_id.get(None)
    logging.exception(f"Unhandled exception occurred. Trace ID: {trace_id}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later.", "trace_id": trace_id}
    )


matching_engine = TransactionMatchingEngine()

# Enforced auth setting: default is False for local MVP dashboard compliance
SYNQ_ENFORCE_AUTH = os.environ.get("SYNQ_ENFORCE_AUTH", "false").lower() in ("true", "1", "yes")

# Auth wrapper dependency
def verify_role(allowed_roles: List[str]):
    def dependency(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
        if not SYNQ_ENFORCE_AUTH:
            if authorization:
                try:
                    payload = get_current_user_payload(authorization)
                    return payload
                except Exception:
                    pass
            # Bypass auth using admin_compliance role to avoid context limits
            return {"sub": "mock-user", "role": "admin_compliance", "customer_id": "c1", "merchant_id": "m1"}
            
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header missing"
            )

            
        payload = get_current_user_payload(authorization)
        role = payload.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied for your role scope"
            )
        return payload
    return dependency

# Helper to log agent steps for console
def log_agent_call(session, agent_name: str, input_data: Any, output_data: Any):
    trace = request_trace_id.get(None)
    log_entry = DBAgentLog(
        timestamp=datetime.datetime.now().strftime("%H:%M:%S"),
        agent=agent_name,
        input_data=str(input_data),
        output_data=str(output_data),
        trace_id=trace
    )
    session.add(log_entry)

    # Keep last 50 logs - prune older logs in the table
    logs_count = session.query(DBAgentLog).count()
    if logs_count > 50:
        oldest_logs = session.query(DBAgentLog).order_by(DBAgentLog.log_id.asc()).limit(logs_count - 50).all()
        for old in oldest_logs:
            session.delete(old)

# Initial Demo Data Setup in Database
def init_demo_data_db(session):
    # Seed Users first if they don't exist
    if session.query(DBUser).count() == 0:
        admin_hash, admin_salt = get_password_hash("admin123")
        m1_hash, m1_salt = get_password_hash("merchant123")
        c1_hash, c1_salt = get_password_hash("consumer123")
        c2_hash, c2_salt = get_password_hash("consumer123")
        c3_hash, c3_salt = get_password_hash("consumer123")

        u_admin = DBUser(username="admin", hashed_password=admin_hash, salt=admin_salt, role="admin_compliance")
        u_m1 = DBUser(username="merchant_m1", hashed_password=m1_hash, salt=m1_salt, role="merchant", merchant_id="m1")
        u_c1 = DBUser(username="consumer_c1", hashed_password=c1_hash, salt=c1_salt, role="consumer", customer_id="c1")
        u_c2 = DBUser(username="consumer_c2", hashed_password=c2_hash, salt=c2_salt, role="consumer", customer_id="c2")
        u_c3 = DBUser(username="consumer_c3", hashed_password=c3_hash, salt=c3_salt, role="consumer", customer_id="c3")

        session.add_all([u_admin, u_m1, u_c1, u_c2, u_c3])
        session.flush()

    # Check if merchant data already exists
    if session.query(DBMerchant).count() > 0:
        return
    
    # 1. Setup Merchants
    m1 = DBMerchant(
        merchant_id="m1", name="Starbucks", category="Coffee",
        onboarded=True, verification_status="Verified", address="456 Market St, SF",
        latitude=37.7891, longitude=-122.4014
    )
    m2 = DBMerchant(
        merchant_id="m2", name="Olive Garden", category="Dining",
        onboarded=True, verification_status="Verified", address="789 Mission St, SF",
        latitude=37.7849, longitude=-122.4085
    )
    m3 = DBMerchant(
        merchant_id="m3", name="Target Store", category="Retail",
        onboarded=True, verification_status="Verified", address="123 Bush St, SF",
        latitude=37.7915, longitude=-122.4025
    )
    m4 = DBMerchant(
        merchant_id="m4", name="Planet Fitness", category="Fitness",
        onboarded=True, verification_status="Verified", address="101 Spear St, SF",
        latitude=37.7901, longitude=-122.3921
    )
    m5 = DBMerchant(
        merchant_id="m5", name="Delta Air Lines", category="Travel",
        onboarded=True, verification_status="Verified", address="SFO Terminal 1",
        latitude=37.6213, longitude=-122.3790
    )
    m6 = DBMerchant(
        merchant_id="m6", name="Whole Foods", category="Grocery",
        onboarded=True, verification_status="Verified", address="2001 Market St, SF",
        latitude=37.7684, longitude=-122.4272
    )
    m7 = DBMerchant(
        merchant_id="m7", name="AMC Theatres", category="Entertainment",
        onboarded=True, verification_status="Verified", address="1000 Van Ness Ave, SF",
        latitude=37.7858, longitude=-122.4218
    )
    m8 = DBMerchant(
        merchant_id="m8", name="Best Buy", category="Electronics",
        onboarded=True, verification_status="Verified", address="1717 Harrison St, SF",
        latitude=37.7695, longitude=-122.4125
    )
    m9 = DBMerchant(
        merchant_id="m9", name="Zara", category="Apparel",
        onboarded=True, verification_status="Verified", address="250 Post St, SF",
        latitude=37.7888, longitude=-122.4045
    )
    m10 = DBMerchant(
        merchant_id="m10", name="Chevron", category="Gas & Automotive",
        onboarded=True, verification_status="Verified", address="3600 Geary Blvd, SF",
        latitude=37.7812, longitude=-122.4578
    )
    m11 = DBMerchant(
        merchant_id="m11", name="Sephora", category="Beauty & Wellness",
        onboarded=True, verification_status="Verified", address="865 Market St, SF",
        latitude=37.7842, longitude=-122.4075
    )
    
    session.add_all([m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11])

    # 2. Setup Customers
    c1 = DBCustomer(
        customer_id="c1",
        name="Alice Vance",
        email="alice.vance@gmail.com",
        products=json.dumps(["Debit Card", "Rewards Credit Card"]),
        accumulated_cashback=15.40,
        redemption_count=3,
        rewards_history=json.dumps([
            {"redemption_id": "r1", "campaign_id": "c100", "merchant_name": "Starbucks", "amount": 1.02, "transaction_amount": 6.80, "timestamp": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()}
        ]),
        affinity_scores=json.dumps({
            "Dining": 4.5,
            "Coffee": 9.2,
            "Travel": 1.0,
            "Retail": 3.5,
            "Fitness": 6.8,
            "Grocery": 7.2,
            "Entertainment": 5.0,
            "Electronics": 4.0,
            "Apparel": 6.5,
            "Gas & Automotive": 3.0,
            "Beauty & Wellness": 8.0
        }),
        personalization=True,
        notifications=True,
        location=True,
        age=28,
        gender="Female",
        income_bracket="Medium",
        home_latitude=37.7895,
        home_longitude=-122.4014
    )

    c2 = DBCustomer(
        customer_id="c2",
        name="Bob Miller",
        email="bob.miller@outlook.com",
        products=json.dumps(["Premium Credit Card"]),
        accumulated_cashback=42.50,
        redemption_count=5,
        rewards_history="[]",
        affinity_scores=json.dumps({
            "Dining": 8.8,
            "Coffee": 3.0,
            "Travel": 7.5,
            "Retail": 6.2,
            "Fitness": 2.0,
            "Grocery": 5.5,
            "Entertainment": 9.0,
            "Electronics": 8.5,
            "Apparel": 4.0,
            "Gas & Automotive": 7.0,
            "Beauty & Wellness": 2.5
        }),
        personalization=True,
        notifications=False,
        location=True,
        age=45,
        gender="Male",
        income_bracket="High",
        home_latitude=37.7749,
        home_longitude=-122.4194
    )

    c3 = DBCustomer(
        customer_id="c3",
        name="Charlie Smith",
        email="charlie.smith@yahoo.com",
        products=json.dumps(["Debit Card"]),
        accumulated_cashback=0.0,
        redemption_count=0,
        rewards_history="[]",
        affinity_scores=json.dumps({cat.value: 1.0 for cat in Category}),
        personalization=True,
        notifications=True,
        location=True,
        age=19,
        gender="Non-Binary",
        income_bracket="Low",
        home_latitude=37.7599,
        home_longitude=-122.4348
    )

    session.add_all([c1, c2, c3])
    session.flush()

    # Seeding Customer Transactions
    c1_tx = [
        DBCustomerTransaction(transaction_id="tx1", customer_id="c1", merchant_name="Starbucks", category="Coffee", amount=6.80, timestamp=datetime.datetime.now() - datetime.timedelta(days=1)),
        DBCustomerTransaction(transaction_id="tx2", customer_id="c1", merchant_name="Starbucks", category="Coffee", amount=5.20, timestamp=datetime.datetime.now() - datetime.timedelta(days=2)),
        DBCustomerTransaction(transaction_id="tx3", customer_id="c1", merchant_name="Blue Bottle Coffee", category="Coffee", amount=8.50, timestamp=datetime.datetime.now() - datetime.timedelta(days=3)),
        DBCustomerTransaction(transaction_id="tx4", customer_id="c1", merchant_name="McDonalds", category="Dining", amount=12.40, timestamp=datetime.datetime.now() - datetime.timedelta(days=4)),
        DBCustomerTransaction(transaction_id="tx5", customer_id="c1", merchant_name="Planet Fitness", category="Fitness", amount=29.99, timestamp=datetime.datetime.now() - datetime.timedelta(days=15)),
    ]
    
    c2_tx = [
        DBCustomerTransaction(transaction_id="tx6", customer_id="c2", merchant_name="Olive Garden", category="Dining", amount=85.50, timestamp=datetime.datetime.now() - datetime.timedelta(days=1)),
        DBCustomerTransaction(transaction_id="tx7", customer_id="c2", merchant_name="Uber Eats", category="Dining", amount=42.00, timestamp=datetime.datetime.now() - datetime.timedelta(days=2)),
        DBCustomerTransaction(transaction_id="tx8", customer_id="c2", merchant_name="Target Store", category="Retail", amount=120.00, timestamp=datetime.datetime.now() - datetime.timedelta(days=5)),
        DBCustomerTransaction(transaction_id="tx9", customer_id="c2", merchant_name="Delta Air Lines", category="Travel", amount=350.00, timestamp=datetime.datetime.now() - datetime.timedelta(days=8)),
    ]

    session.add_all(c1_tx + c2_tx)

    # 3. Setup Campaigns
    camp1 = DBCampaign(
        campaign_id="camp_starbucks",
        merchant_id="m1",
        merchant_name="Starbucks",
        name="Starbucks Morning Fuel",
        category="Coffee",
        offer_type="Cashback Percentage",
        offer_value=15.0,
        min_spend=5.0,
        budget=1000.0,
        remaining_budget=950.0,
        duration_days=30,
        audience_segments=json.dumps(["Coffee Buyers", "Local Radius"]),
        marketing_copy="Power through your morning! Get 15% cashback at any local Starbucks with your linked card.",
        legal_disclosure="Valid on coffee purchases. Min spend $5. Max reward $3. Budget caps apply.",
        status="Active",
        impressions=120,
        activations=45,
        redemptions=5,
        total_spend_driven=34.0,
        total_cashback_paid=5.10
    )

    camp2 = DBCampaign(
        campaign_id="camp_olive_garden",
        merchant_id="m2",
        merchant_name="Olive Garden",
        name="Olive Garden Dine Out",
        category="Dining",
        offer_type="Cashback Percentage",
        offer_value=10.0,
        min_spend=20.0,
        budget=2000.0,
        remaining_budget=1920.0,
        duration_days=45,
        audience_segments=json.dumps(["Frequent Diners", "High Spenders"]),
        marketing_copy="Gather around the table! Enjoy 10% cashback on delicious Italian dining at Olive Garden.",
        legal_disclosure="Valid on lunch or dinner. Min spend $20. Max reward $10 per bill.",
        status="Active",
        impressions=85,
        activations=22,
        redemptions=2,
        total_spend_driven=160.0,
        total_cashback_paid=16.0
    )

    camp3 = DBCampaign(
        campaign_id="camp_target",
        merchant_id="m3",
        merchant_name="Target Store",
        name="Target Essentials Deal",
        category="Retail",
        offer_type="Cashback Flat Amount",
        offer_value=5.0,
        min_spend=30.0,
        budget=5000.0,
        remaining_budget=5000.0,
        duration_days=30,
        audience_segments=json.dumps(["Rewards Customers", "High Spenders"]),
        marketing_copy="Stock up on everyday essentials. Get $5 flat cashback on purchases over $30.",
        legal_disclosure="Limit one redemption per day. Transaction must exceed $30 before taxes.",
        status="Active",
        impressions=310,
        activations=112,
        redemptions=0,
        total_spend_driven=0.0,
        total_cashback_paid=0.0
    )

    # Compliance flagged draft
    camp4 = DBCampaign(
        campaign_id="camp_draft_bad",
        merchant_id="m1",
        merchant_name="Starbucks",
        name="Starbucks Brews & Beer Special",
        category="Coffee",
        offer_type="Cashback Percentage",
        offer_value=20.0,
        min_spend=0.0,
        budget=500.0,
        remaining_budget=500.0,
        duration_days=10,
        audience_segments=json.dumps(["Coffee Buyers"]),
        marketing_copy="Grab a hot coffee or a draft beer! Guaranteed double cashback with no risk of missing out!",
        legal_disclosure="No limits! Spend anything!",
        status="Pending Compliance Review",
        compliance_feedback="Flagged by AI: Contains restricted category ALCOHOL ('beer') and DECEPTIVE marketing claims ('guaranteed double cashback', 'no risk'). Required minimum spend or caps in disclosure."
    )

    session.add_all([camp1, camp2, camp3, camp4])
    session.flush()

    # Automatically activate Starbucks and Olive Garden for Alice
    session.add(DBActiveOffer(customer_id="c1", campaign_id="camp_starbucks"))
    session.add(DBActiveOffer(customer_id="c1", campaign_id="camp_olive_garden"))
    # Activate Target for Bob
    session.add(DBActiveOffer(customer_id="c2", campaign_id="camp_target"))

# Initialize database tables & seed data on FastAPI startup
@app.on_event("startup")
def startup_event():
    setup_logging()
    logging.info("Synq Commerce Network API starting...")
    init_db()
    with get_db_session() as session:
        init_demo_data_db(session)

# -----------------------------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest):
    with get_db_session() as session:
        user = session.query(DBUser).filter_by(username=req.username).first()
        if not user or not verify_password(req.password, user.hashed_password, user.salt):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
            
        token_data = {"sub": user.username, "role": user.role}
        if user.customer_id:
            token_data["customer_id"] = user.customer_id
        if user.merchant_id:
            token_data["merchant_id"] = user.merchant_id
            
    token = create_access_token(token_data)
    return {"access_token": token, "token_type": "bearer", "role": token_data["role"]}

@app.post("/api/auth/register", response_model=User)
def register(req: UserRegisterRequest):
    with get_db_session() as session:
        # Check if username already exists
        existing = session.query(DBUser).filter_by(username=req.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
        
        # Verify role dependencies
        if req.role == "consumer" and not req.customer_id:
            customer_id = f"c_{uuid.uuid4().hex[:6]}"
            new_cust = DBCustomer(
                customer_id=customer_id,
                name=req.username.capitalize(),
                email=f"{req.username}@example.com",
                products=json.dumps(["Debit Card"]),
                accumulated_cashback=0.0,
                redemption_count=0,
                rewards_history="[]",
                affinity_scores=json.dumps({cat.value: 1.0 for cat in Category}),
                personalization=True,
                notifications=True,
                location=True
            )
            session.add(new_cust)
            req.customer_id = customer_id
        elif req.role == "merchant" and not req.merchant_id:
            merchant_id = f"m_{uuid.uuid4().hex[:6]}"
            new_merch = DBMerchant(
                merchant_id=merchant_id,
                name=f"{req.username.capitalize()} Store",
                category="Dining",
                onboarded=True,
                verification_status="Verified",
                address="123 Main St",
                latitude=37.7749,
                longitude=-122.4194
            )
            session.add(new_merch)
            req.merchant_id = merchant_id
            
        hashed_pwd, salt = get_password_hash(req.password)
        db_user = DBUser(
            username=req.username,
            hashed_password=hashed_pwd,
            salt=salt,
            role=req.role,
            customer_id=req.customer_id,
            merchant_id=req.merchant_id
        )
        session.add(db_user)
        session.flush()
        return from_db_user(db_user)


# -----------------------------------------------------------------------------
# MERCHANT ENDPOINTS
# -----------------------------------------------------------------------------
class OnboardRequest(BaseModel):
    name: str
    category: Category
    address: str
    latitude: float
    longitude: float

@app.post("/api/onboard/merchant")
def onboard_merchant(req: OnboardRequest, user=Depends(verify_role(["admin_compliance"]))):
    merchant_id = f"m_{uuid.uuid4().hex[:6]}"
    merchant = Merchant(
        merchant_id=merchant_id,
        name=req.name,
        category=req.category,
        onboarded=True,
        verification_status="Verified",
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude
    )
    
    with get_db_session() as session:
        db_m = to_db_merchant(merchant)
        session.add(db_m)
    
    return {"status": "success", "merchant": merchant}

@app.get("/api/merchants")
def list_merchants():
    with get_db_session() as session:
        db_merchants = session.query(DBMerchant).all()
        return [from_db_merchant(m) for m in db_merchants]

@app.get("/api/merchants/{merchant_id}/analytics")
def get_merchant_analytics(merchant_id: str, user=Depends(verify_role(["merchant", "admin_compliance"]))):
    # If role is merchant, restrict to their own merchant id
    if SYNQ_ENFORCE_AUTH and user.get("role") == "merchant" and user.get("merchant_id") != merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this merchant context")

    with get_db_session() as session:
        merchant = session.query(DBMerchant).filter_by(merchant_id=merchant_id).first()
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
            
        merchant_campaigns = session.query(DBCampaign).filter_by(merchant_id=merchant_id).all()
        
        total_impressions = sum(c.impressions for c in merchant_campaigns)
        total_activations = sum(c.activations for c in merchant_campaigns)
        total_redemptions = sum(c.redemptions for c in merchant_campaigns)
        total_spend_driven = sum(c.total_spend_driven for c in merchant_campaigns)
        total_cashback_paid = sum(c.total_cashback_paid for c in merchant_campaigns)
        
        # Calculate average ROI
        roi = round((total_spend_driven / total_cashback_paid), 2) if total_cashback_paid > 0 else 0.0
        
        # Filter settlement reports for this merchant
        settlements = session.query(DBBillingRecord).filter_by(merchant_id=merchant_id).all()

        return {
            "merchant_id": merchant_id,
            "merchant_name": merchant.name,
            "metrics": {
                "campaigns_count": len(merchant_campaigns),
                "impressions": total_impressions,
                "activations": total_activations,
                "redemptions": total_redemptions,
                "spend_driven": total_spend_driven,
                "cashback_paid": total_cashback_paid,
                "roi": roi
            },
            "campaigns": [from_db_campaign(c) for c in merchant_campaigns],
            "settlements": [from_db_billing(s) for s in settlements]
        }

class CampaignCreateRequest(BaseModel):
    merchant_id: str
    name: str
    offer_type: OfferType
    offer_value: float
    min_spend: float
    budget: float
    duration_days: int
    audience_segments: List[Segment]
    marketing_copy: str
    legal_disclosure: str

@app.post("/api/merchants/{merchant_id}/campaigns")
def create_campaign(merchant_id: str, req: CampaignCreateRequest, user=Depends(verify_role(["merchant", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "merchant" and user.get("merchant_id") != merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this merchant context")

    with get_db_session() as session:
        merchant = session.query(DBMerchant).filter_by(merchant_id=merchant_id).first()
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")

        campaign_id = f"camp_{uuid.uuid4().hex[:8]}"
        
        # Run Compliance Agent (AG-008) in-line
        review = ComplianceAgent.review_campaign(
            campaign_name=req.name,
            merchant_category=merchant.category,
            marketing_copy=req.marketing_copy,
            legal_disclosure=req.legal_disclosure
        )
        
        log_agent_call(
            session=session,
            agent_name="Compliance Agent (AG-008)",
            input_data={"name": req.name, "copy": req.marketing_copy, "disclosure": req.legal_disclosure},
            output_data=review.model_dump()
        )

        # Create Campaign
        status = CampaignStatus.ACTIVE if review.is_compliant else CampaignStatus.PENDING_COMPLIANCE
        feedback = None if review.is_compliant else "; ".join(review.flagged_reasons)
        
        campaign = Campaign(
            campaign_id=campaign_id,
            merchant_id=merchant_id,
            merchant_name=merchant.name,
            name=req.name,
            category=Category(merchant.category),
            offer_type=req.offer_type,
            offer_value=req.offer_value,
            min_spend=req.min_spend,
            budget=req.budget,
            remaining_budget=req.budget,
            duration_days=req.duration_days,
            audience_segments=req.audience_segments,
            marketing_copy=req.marketing_copy,
            legal_disclosure=req.legal_disclosure,
            status=status,
            compliance_feedback=feedback
        )
        
        db_camp = to_db_campaign(campaign)
        session.add(db_camp)
        
        return {
            "status": "success",
            "compliance_review": review,
            "campaign": campaign
        }

class AISuggestRequest(BaseModel):
    merchant_id: str
    goal: str

@app.post("/api/merchants/{merchant_id}/ai-suggest")
def ai_suggest_campaign(merchant_id: str, req: AISuggestRequest, user=Depends(verify_role(["merchant", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "merchant" and user.get("merchant_id") != merchant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this merchant context")

    with get_db_session() as session:
        merchant = session.query(DBMerchant).filter_by(merchant_id=merchant_id).first()
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
            
        proposal = CampaignAgent.generate_proposal(
            merchant_name=merchant.name,
            category=merchant.category,
            business_goal=req.goal
        )
        
        log_agent_call(
            session=session,
            agent_name="Merchant Campaign Agent (AG-001)",
            input_data={"merchant": merchant.name, "goal": req.goal},
            output_data=proposal.model_dump()
        )
        
        return proposal

# -----------------------------------------------------------------------------
# CONSUMER ENDPOINTS
# -----------------------------------------------------------------------------
@app.get("/api/consumers")
def list_consumers(user=Depends(verify_role(["admin_compliance"]))):
    with get_db_session() as session:
        db_customers = session.query(DBCustomer).all()
        return [from_db_customer(c) for c in db_customers]

@app.get("/api/consumers/{customer_id}")
def get_customer_360(customer_id: str, user=Depends(verify_role(["consumer", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "consumer" and user.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized for this customer profile")

    with get_db_session() as session:
        db_customer = session.query(DBCustomer).filter_by(customer_id=customer_id).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
            
        customer = from_db_customer(db_customer)
        
        # Recalculate affinities using AffinityAgent (AG-003) to simulate real-time analytics
        profile = AffinityAgent.calculate_affinities(
            customer_id=customer_id,
            transactions_data=[tx.model_dump() for tx in customer.transactions],
            demographics={
                "age": customer.age,
                "gender": customer.gender,
                "income_bracket": customer.income_bracket
            },
            location={
                "home_latitude": customer.home_latitude,
                "home_longitude": customer.home_longitude
            }
        )
        
        # Log the affinity computation
        log_agent_call(
            session=session,
            agent_name="Customer Affinity Agent (AG-003)",
            input_data={"customer_id": customer_id, "tx_count": len(customer.transactions)},
            output_data={"dominant_segment": profile.dominant_segment}
        )

        # Sync calculated affinities to customer model representation in database
        synced_scores = {}
        for aff in profile.affinities:
            for cat in Category:
                if cat.value == aff.category:
                    synced_scores[cat.value] = aff.score
                    break
        db_customer.affinity_scores = json.dumps(synced_scores)
        
        return {
            "customer": from_db_customer(db_customer),
            "affinity_profile": profile
        }

@app.get("/api/consumers/{customer_id}/offers")
def get_offers_feed(
    customer_id: str, 
    latitude: float = Query(None), 
    longitude: float = Query(None),
    user=Depends(verify_role(["consumer", "admin_compliance"]))
):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "consumer" and user.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized for this customer context")

    with get_db_session() as session:
        db_customer = session.query(DBCustomer).filter_by(customer_id=customer_id).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer = from_db_customer(db_customer)

        # Resolve location: device coordinates -> customer home coordinates -> default SF coordinates
        resolved_lat = latitude if latitude is not None else customer.home_latitude
        resolved_lon = longitude if longitude is not None else customer.home_longitude
        
        if resolved_lat is None:
            resolved_lat = 37.7749
        if resolved_lon is None:
            resolved_lon = -122.4194

        # Get active campaigns
        db_active_campaigns = session.query(DBCampaign).filter(DBCampaign.status == "Active").all()
        active_campaigns = [from_db_campaign(c) for c in db_active_campaigns]
        
        # Run Offer Ranking Agent (AG-006) which coordinates scores and explains insights (AG-010)
        ranked = RankingAgent.rank_offers(
            customer=customer, 
            campaigns=active_campaigns,
            customer_lat=resolved_lat,
            customer_lon=resolved_lon
        )
        
        log_agent_call(
            session=session,
            agent_name="Offer Ranking Agent (AG-006)",
            input_data={"customer_id": customer_id, "campaign_count": len(active_campaigns), "lat": resolved_lat, "lon": resolved_lon},
            output_data={"ranked_count": len(ranked.ranked_offers)}
        )

        # Map ranked items to campaigns and inject customer explanations
        feed_offers = []
        activated_ids = matching_engine.get_activated_campaign_ids(customer_id, session)
        
        for item in ranked.ranked_offers:
            campaign = next((c for c in active_campaigns if c.campaign_id == item.campaign_id), None)
            if campaign:
                camp_dict = campaign.model_dump()
                camp_dict["activated"] = campaign.campaign_id in activated_ids
                camp_dict["relevance_score"] = item.score
                camp_dict["user_explanation"] = item.user_explanation
                
                # Make dates JSON serializable
                if isinstance(camp_dict.get("created_at"), datetime.datetime):
                    camp_dict["created_at"] = camp_dict["created_at"].isoformat()
                    
                feed_offers.append(camp_dict)

        # Also build "Trending" and "Nearby" categories for MVP Feed tabs
        trending_offers = sorted(feed_offers, key=lambda x: x.get("activations", 0), reverse=True)
        
        # Real GPS distance checks for "Nearby" using Haversine approximation in km
        import math
        def get_distance_km(lat1, lon1, lat2, lon2):
            if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
                return 999.0
            d_lat = (lat2 - lat1) * 111.0
            d_lon = (lon2 - lon1) * 88.0
            return math.sqrt(d_lat**2 + d_lon**2)

        nearby_offers = []
        for offer in feed_offers:
            db_merchant = session.query(DBMerchant).filter_by(merchant_id=offer["merchant_id"]).first()
            if db_merchant:
                dist = get_distance_km(resolved_lat, resolved_lon, db_merchant.latitude, db_merchant.longitude)
                # Keep offers within a 15 km local radius
                if dist <= 15.0:
                    offer_copy = offer.copy()
                    offer_copy["distance_km"] = round(dist, 2)
                    nearby_offers.append(offer_copy)
                    
        # Fallback if no nearby offers found to prevent empty state in simulator
        if not nearby_offers:
            nearby_offers = [c for c in feed_offers if c["campaign_id"] in ["camp_starbucks", "camp_olive_garden"]]

        return {
            "recommended": feed_offers,
            "nearby": nearby_offers,
            "trending": trending_offers
        }

class ActivateRequest(BaseModel):
    campaign_id: str

@app.post("/api/consumers/{customer_id}/offers/activate")
def activate_offer(customer_id: str, req: ActivateRequest, user=Depends(verify_role(["consumer", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "consumer" and user.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized for this customer context")

    with get_db_session() as session:
        db_customer = session.query(DBCustomer).filter_by(customer_id=customer_id).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
            
        db_campaign = session.query(DBCampaign).filter_by(campaign_id=req.campaign_id).first()
        if not db_campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        matching_engine.activate_offer(customer_id, req.campaign_id, session)
        
        # Increment campaign activation count
        db_campaign.activations += 1
        
        return {"status": "success", "message": f"Campaign {req.campaign_id} activated"}

@app.post("/api/consumers/{customer_id}/offers/deactivate")
def deactivate_offer(customer_id: str, req: ActivateRequest, user=Depends(verify_role(["consumer", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "consumer" and user.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized for this customer context")

    with get_db_session() as session:
        db_customer = session.query(DBCustomer).filter_by(customer_id=customer_id).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
            
        matching_engine.deactivate_offer(customer_id, req.campaign_id, session)
        return {"status": "success", "message": f"Campaign {req.campaign_id} deactivated"}

class TransactionSimulateRequest(BaseModel):
    merchant_name: str
    amount: float

@app.post("/api/consumers/{customer_id}/transactions/simulate")
def simulate_transaction(customer_id: str, req: TransactionSimulateRequest, user=Depends(verify_role(["consumer", "admin_compliance"]))):
    if SYNQ_ENFORCE_AUTH and user.get("role") == "consumer" and user.get("customer_id") != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized for this customer context")

    with get_db_session() as session:
        db_customer = session.query(DBCustomer).filter_by(customer_id=customer_id).first()
        if not db_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer = from_db_customer(db_customer)

        # Find matching merchant to determine category
        matched_merchant = None
        db_merchants = session.query(DBMerchant).all()
        for m in db_merchants:
            if m.name.lower() in req.merchant_name.lower() or req.merchant_name.lower() in m.name.lower():
                matched_merchant = m
                break
                
        category = Category(matched_merchant.category) if matched_merchant else Category.DINING

        # 1. Create Transaction
        transaction_id = f"tx_{uuid.uuid4().hex[:8]}"
        transaction = CustomerTransaction(
            transaction_id=transaction_id,
            merchant_name=req.merchant_name,
            category=category,
            amount=req.amount,
            timestamp=datetime.datetime.now()
        )

        execution_steps = [
            f"Registered new transaction: {req.merchant_name} for ${req.amount:.2f}."
        ]

        # 2. Match transaction against active activated offers
        match_result = matching_engine.match_transaction(
            customer_id=customer_id,
            transaction=transaction,
            session=session
        )

        redemption = None
        billing = None

        if match_result:
            campaign, cashback_amount = match_result
            execution_steps.append(
                f"Match Found! Campaign '{campaign.name}' matches transaction merchant/category. "
                f"Calculating cashback ({campaign.offer_value}% or flat value) = ${cashback_amount:.2f}."
            )

            # 3. Process cashback credit (saves transaction and redemption)
            redemption = CashbackProcessor.process_redemption(
                session=session,
                customer_id=customer_id,
                transaction=transaction,
                campaign_id=campaign.campaign_id,
                cashback_amount=cashback_amount
            )
            execution_steps.append("Cashback credited successfully to rewards account ledger.")

            # 4. Process Settlement Invoice billing
            billing = SettlementEngine.calculate_merchant_fee(session, redemption, campaign.campaign_id)
            execution_steps.append(
                f"Settlement Billing generated: Charged merchant ${billing.cashback_charge:.2f} for cashback, "
                f"plus ${billing.bank_fee:.2f} bank reward commission fee. Total: ${billing.total_charged:.2f}."
            )
        else:
            # If no match, save the bare transaction anyway to customer transaction history
            db_tx = to_db_transaction(transaction, customer_id)
            session.add(db_tx)
            execution_steps.append("Transaction scanned. No active matching activated card-linked offers found.")

        # Prepare JSON response items
        redemption_dict = redemption.model_dump() if redemption else None
        if redemption_dict and isinstance(redemption_dict.get("timestamp"), datetime.datetime):
            redemption_dict["timestamp"] = redemption_dict["timestamp"].isoformat()

        billing_dict = billing.model_dump() if billing else None
        if billing_dict and isinstance(billing_dict.get("timestamp"), datetime.datetime):
            billing_dict["timestamp"] = billing_dict["timestamp"].isoformat()

        tx_dict = transaction.model_dump()
        if isinstance(tx_dict.get("timestamp"), datetime.datetime):
            tx_dict["timestamp"] = tx_dict["timestamp"].isoformat()

        return {
            "status": "success",
            "matched": match_result is not None,
            "transaction": tx_dict,
            "redemption": redemption_dict,
            "billing": billing_dict,
            "logs": execution_steps
        }

# -----------------------------------------------------------------------------
# ADMIN & COMPLIANCE ENDPOINTS
# -----------------------------------------------------------------------------
@app.get("/api/admin/compliance/pending")
def list_pending_compliance(user=Depends(verify_role(["admin_compliance"]))):
    with get_db_session() as session:
        db_pending = session.query(DBCampaign).filter_by(status="Pending Compliance Review").all()
        res = []
        for db_c in db_pending:
            camp = from_db_campaign(db_c)
            camp_dict = camp.model_dump()
            camp_dict["created_at"] = camp.created_at.isoformat()
            reasons = db_c.compliance_feedback.split("; ") if db_c.compliance_feedback else ["Flagged for restricted items."]
            camp_dict["compliance_feedback"] = db_c.compliance_feedback
            camp_dict["compliance_review"] = {
                "is_compliant": False,
                "flagged_reasons": reasons
            }
            res.append(camp_dict)
        return res

class ReviewDecisionRequest(BaseModel):
    campaign_id: str
    approved: bool
    compliance_feedback: Optional[str] = None

@app.post("/api/admin/compliance/review")
def review_campaign_decision(req: ReviewDecisionRequest, user=Depends(verify_role(["admin_compliance"]))):
    with get_db_session() as session:
        db_campaign = session.query(DBCampaign).filter_by(campaign_id=req.campaign_id).first()
        if not db_campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if req.approved:
            db_campaign.status = "Active"
            db_campaign.compliance_feedback = None
        else:
            db_campaign.status = "Rejected"
            db_campaign.compliance_feedback = req.compliance_feedback or "Rejected by Compliance Officer."

        campaign = from_db_campaign(db_campaign)
        return {"status": "success", "campaign": campaign}

# -----------------------------------------------------------------------------
# CONSOLE LOGS & DIAGNOSTICS
# -----------------------------------------------------------------------------
@app.get("/api/admin/agent-logs")
def get_agent_logs(user=Depends(verify_role(["admin_compliance", "merchant", "consumer"]))):
    with get_db_session() as session:
        db_logs = session.query(DBAgentLog).order_by(DBAgentLog.log_id.desc()).limit(50).all()
        return [
            {
                "timestamp": l.timestamp,
                "agent": l.agent,
                "input": l.input_data,
                "output": l.output_data,
                "trace_id": l.trace_id
            }
            for l in db_logs
        ]


# -----------------------------------------------------------------------------
# HEALTH CHECK ENDPOINT
# -----------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Liveness and readiness probe for container orchestration."""
    try:
        with get_db_session() as session:
            from sqlalchemy import text
            session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat(),
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failure: {str(e)}"
        )

# -----------------------------------------------------------------------------
# STATIC FILE SERVING
# -----------------------------------------------------------------------------
# Mount static folder
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

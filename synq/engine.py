import uuid
import datetime
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from synq.db_models import DBCampaign, DBCustomer, DBCustomerTransaction, DBRedemption, DBBillingRecord, DBActiveOffer
from synq.models import Campaign, Customer, CustomerTransaction, Redemption, BillingRecord, Category, OfferType, CampaignStatus
from synq.database import from_db_campaign, from_db_redemption, from_db_billing, to_db_redemption, to_db_billing, to_db_transaction

class TransactionMatchingEngine:
    def activate_offer(self, customer_id: str, campaign_id: str, session: Session) -> bool:
        # Check if already active
        existing = session.query(DBActiveOffer).filter_by(customer_id=customer_id, campaign_id=campaign_id).first()
        if existing:
            return True
        
        active = DBActiveOffer(customer_id=customer_id, campaign_id=campaign_id)
        session.add(active)
        return True

    def deactivate_offer(self, customer_id: str, campaign_id: str, session: Session) -> bool:
        existing = session.query(DBActiveOffer).filter_by(customer_id=customer_id, campaign_id=campaign_id).first()
        if existing:
            session.delete(existing)
            return True
        return False

    def get_activated_campaign_ids(self, customer_id: str, session: Session) -> List[str]:
        records = session.query(DBActiveOffer).filter_by(customer_id=customer_id).all()
        return [r.campaign_id for r in records]

    def match_transaction(
        self, 
        customer_id: str, 
        transaction: CustomerTransaction, 
        session: Session
    ) -> Optional[Tuple[Campaign, float]]:
        """Matches a customer transaction against active campaigns in the database."""
        # 1. Get all active campaign IDs activated by this customer
        activated_ids = self.get_activated_campaign_ids(customer_id, session)
        if not activated_ids:
            return None

        # 2. Query campaigns
        db_campaigns = session.query(DBCampaign).filter(
            DBCampaign.campaign_id.in_(activated_ids),
            DBCampaign.status == "Active"
        ).all()

        for db_campaign in db_campaigns:
            # Check merchant match (case-insensitive name checking)
            campaign_merchant_name = db_campaign.merchant_name.lower().strip()
            tx_merchant_name = transaction.merchant_name.lower().strip()
            
            if campaign_merchant_name not in tx_merchant_name and tx_merchant_name not in campaign_merchant_name:
                continue

            # Check min spend
            if transaction.amount < db_campaign.min_spend:
                continue

            # Calculate cashback amount
            cashback = 0.0
            if db_campaign.offer_type == "Cashback Percentage":
                cashback = transaction.amount * (db_campaign.offer_value / 100.0)
            elif db_campaign.offer_type == "Cashback Flat Amount":
                cashback = db_campaign.offer_value
            elif db_campaign.offer_type == "Points Multiplier":
                cashback = transaction.amount * db_campaign.offer_value * 0.01

            cashback = round(cashback, 2)

            # Check budget
            if db_campaign.remaining_budget < cashback:
                continue

            # Convert to Pydantic Campaign model for return compatibility
            campaign = from_db_campaign(db_campaign)
            return campaign, cashback

        return None


class CashbackProcessor:
    @staticmethod
    def process_redemption(
        session: Session,
        customer_id: str,
        transaction: CustomerTransaction,
        campaign_id: str,
        cashback_amount: float
    ) -> Redemption:
        """Deducts campaign budget, registers rewards in customer ledger, and logs redemption.
        
        Uses pessimistic locking (with_for_update) to prevent race conditions in concurrent redemptions.
        """
        # 1. Fetch Campaign and Customer with update lock
        db_campaign = session.query(DBCampaign).filter(DBCampaign.campaign_id == campaign_id).with_for_update().first()
        db_customer = session.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).with_for_update().first()

        if not db_campaign or not db_customer:
            raise ValueError("Campaign or Customer not found during redemption processing")

        # 2. Update Campaign Stats
        db_campaign.remaining_budget = round(db_campaign.remaining_budget - cashback_amount, 2)
        db_campaign.redemptions += 1
        db_campaign.total_spend_driven = round(db_campaign.total_spend_driven + transaction.amount, 2)
        db_campaign.total_cashback_paid = round(db_campaign.total_cashback_paid + cashback_amount, 2)

        # If budget exhausted, set completed
        if db_campaign.remaining_budget <= 0:
            db_campaign.status = "Completed"

        # 3. Update Customer Rewards Ledger
        db_customer.accumulated_cashback = round(db_customer.accumulated_cashback + cashback_amount, 2)
        db_customer.redemption_count += 1
        
        # Load and append to customer rewards history
        import json
        try:
            history = json.loads(db_customer.rewards_history or "[]")
        except Exception:
            history = []

        redemption_id = str(uuid.uuid4())
        redemption_event = {
            "redemption_id": redemption_id,
            "campaign_id": campaign_id,
            "merchant_name": db_campaign.merchant_name,
            "amount": cashback_amount,
            "transaction_amount": transaction.amount,
            "timestamp": datetime.datetime.now().isoformat()
        }
        history.append(redemption_event)
        db_customer.rewards_history = json.dumps(history)

        # 4. Save Customer Transaction to DB
        db_tx = to_db_transaction(transaction, customer_id)
        session.add(db_tx)

        # 5. Create DB Redemption
        db_redemption = DBRedemption(
            redemption_id=redemption_id,
            customer_id=customer_id,
            campaign_id=campaign_id,
            merchant_name=db_campaign.merchant_name,
            transaction_id=transaction.transaction_id,
            transaction_amount=transaction.amount,
            cashback_amount=cashback_amount,
            timestamp=datetime.datetime.now()
        )
        session.add(db_redemption)
        session.flush() # Populate generated attributes/verify constraints

        return from_db_redemption(db_redemption)


class SettlementEngine:
    @staticmethod
    def calculate_merchant_fee(
        session: Session,
        redemption: Redemption, 
        campaign_id: str
    ) -> BillingRecord:
        """Calculates billing record details for merchant invoice and persists it."""
        db_campaign = session.query(DBCampaign).filter(DBCampaign.campaign_id == campaign_id).first()
        if not db_campaign:
            raise ValueError("Campaign not found during merchant fee calculation")

        cashback_charge = redemption.cashback_amount
        bank_fee = round(0.25 + (cashback_charge * 0.10), 2)
        total_charged = round(cashback_charge + bank_fee, 2)

        db_billing = DBBillingRecord(
            record_id=str(uuid.uuid4()),
            redemption_id=redemption.redemption_id,
            merchant_id=db_campaign.merchant_id,
            merchant_name=db_campaign.merchant_name,
            cashback_charge=cashback_charge,
            bank_fee=bank_fee,
            total_charged=total_charged,
            settled=False,
            timestamp=datetime.datetime.now()
        )
        session.add(db_billing)
        session.flush()

        return from_db_billing(db_billing)

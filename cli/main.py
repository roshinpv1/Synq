import os
import sys
import time
import webbrowser
import typer
import uvicorn
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Import core Synq components
from synq.models import Customer, CustomerTransaction, Category, CardProduct, Campaign, CampaignStatus, OfferType
from synq.engine import TransactionMatchingEngine, CashbackProcessor, SettlementEngine

console = Console()

app = typer.Typer(
    name="Synq",
    help="Synq CLI: Banking-Powered Commerce Intelligence Network Framework",
    add_completion=True,
)

# ASCII Art for Synq Logo
WELCOME_ASCII = """
   _____ __  __ _   _  ____ 
  / ____|  \/  | \ | |/ __ \\
 | (___ | \  / |  \| | |  | |
  \___ \| |\/| | . ` | |  | |
  ____) | |  | | |\  | |__| |
 |_____/|_|  |_|_| \_|\___\_\\
                            
"""

def print_welcome():
    console.print(WELCOME_ASCII, style="bold purple")
    console.print(
        Panel(
            "[bold green]Synq Commerce Network CLI[/bold green]\n"
            "Banking-Powered Commerce Intelligence Network Platform",
            border_style="purple"
        )
    )

@app.command()
def web(
    port: int = typer.Option(8000, help="Port to run the Synq server on"),
    host: str = typer.Option("127.0.0.1", help="Host to bind the Synq server to"),
    workers: int = typer.Option(1, help="Number of uvicorn worker processes"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open default web browser"),
):
    """Launch the Synq Web Portal and backend API server."""
    print_welcome()
    
    workers_env = int(os.environ.get("SYNQ_WORKERS", str(workers)))
    console.print(f"[bold info]Starting Synq API & Portal on http://{host}:{port} with {workers_env} workers...[/bold info]")
    
    # Simple delay to open browser
    if not no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")
        
        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    # Import in-line to avoid loading uvicorn dependencies early on CLI commands list
    if workers_env > 1:
        uvicorn.run("synq.server:app", host=host, port=port, workers=workers_env)
    else:
        from synq.server import app as fastapi_app
        uvicorn.run(fastapi_app, host=host, port=port)

@app.command()
def simulate(
    customer_name: str = typer.Option("Alice Vance", help="Simulate a transaction for this customer"),
    merchant: str = typer.Option("Starbucks", help="Merchant where the card is swiped"),
    amount: float = typer.Option(12.50, help="Amount spent in quotes currency"),
):
    """Simulate a credit/debit card transaction swipe and run offer matching engine."""
    print_welcome()
    
    # 1. Setup mock customer
    c = Customer(
        customer_id="c1",
        name=customer_name,
        email="alice.vance@gmail.com",
        products=[CardProduct.REWARDS_CREDIT],
        transactions=[],
        affinity_scores={Category.COFFEE: 9.0, Category.DINING: 4.0}
    )

    # 2. Setup mock campaign
    camp = Campaign(
        campaign_id="camp_starbucks",
        merchant_id="m1",
        merchant_name="Starbucks",
        name="Starbucks Fuel Offer",
        category=Category.COFFEE,
        offer_type=OfferType.CASHBACK_PERCENT,
        offer_value=15.0,
        min_spend=5.0,
        budget=1000.0,
        remaining_budget=1000.0,
        duration_days=30,
        status=CampaignStatus.ACTIVE
    )

    # 3. Setup match engine and activate
    engine = TransactionMatchingEngine()
    engine.activate_offer(c.customer_id, camp.campaign_id)

    # Output parameters
    tx_table = Table(title="Card Swipe Parameters", box=box.ROUNDED, border_style="cyan")
    tx_table.add_column("Parameter", style="cyan")
    tx_table.add_column("Value", style="green")
    tx_table.add_row("Customer Profile", c.name)
    tx_table.add_row("Merchant Swiped", merchant)
    tx_table.add_row("Transaction Spend", f"${amount:.2f}")
    tx_table.add_row("Card Program", c.products[0].value)
    console.print(tx_table)

    console.print("\n[bold info]Processing transaction matching...[/bold info]")
    
    # Simulate transaction
    tx = CustomerTransaction(
        transaction_id="tx_cli_sim",
        merchant_name=merchant,
        category=Category.COFFEE,
        amount=amount,
        timestamp=time.time()
    )

    match_result = engine.match_transaction(c, tx, [camp])
    
    if match_result:
        matched_camp, cashback = match_result
        console.print(f"[bold green]✔ Offer Matched! Validating campaign: '{matched_camp.name}'[/bold green]")
        
        redemption = CashbackProcessor.process_redemption(c, tx, matched_camp, cashback)
        billing = SettlementEngine.calculate_merchant_fee(redemption, matched_camp)
        
        # Output results panel
        res_table = Table(title="Settlement Settlement Engine Ledgers", box=box.ROUNDED, border_style="green")
        res_table.add_column("Ledger", style="bold green")
        res_table.add_column("Amount", style="green")
        res_table.add_column("Description", style="white")
        
        res_table.add_row("Consumer Cashback", f"${redemption.cashback_amount:.2f}", f"Credited to {c.name}'s Rewards balance")
        res_table.add_row("Merchant Invoice charge", f"${billing.cashback_charge:.2f}", "Billed back to Starbucks to cover cashback")
        res_table.add_row("Bank Commission fee", f"${billing.bank_fee:.2f}", "Regional Bank net revenue fee share (10% + $0.25 msf)")
        res_table.add_row("Total Merchant settlement", f"${billing.total_charged:.2f}", "Total settlement charged invoice")
        console.print(res_table)
        
    else:
        console.print("[bold red]✘ No Offer Match Found.[/bold red]")
        console.print("[dim]Ensure transaction merchant/amount satisfies active campaigns activated by the customer.[/dim]")

if __name__ == "__main__":
    app()

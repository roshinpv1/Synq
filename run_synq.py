import os
import sys

# Add current folder to path to enable package import resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from synq.server import app

if __name__ == "__main__":
    print("=========================================================================")
    print("Starting Synq Banking-Powered Commerce Intelligence Network Dashboard...")
    print("=========================================================================")
    
    host = os.environ.get("SYNQ_HOST", "127.0.0.1")
    port = int(os.environ.get("SYNQ_PORT", "8000"))
    workers = int(os.environ.get("SYNQ_WORKERS", "1"))
    
    # In ASGI production setup, passing uvicorn.run(app) with workers > 1 requires passing app import path string instead of app instance
    app_target = "synq.server:app" if workers > 1 else app
    
    uvicorn.run(app_target, host=host, port=port, workers=workers)

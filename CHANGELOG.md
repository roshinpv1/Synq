# Changelog

All notable changes to the Synq Banking-Powered Commerce Intelligence Network are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] — 2026-06-22

### Added
- **Explicit Dependency Declarations:** Added `pydantic` and `sqlalchemy` directly to `pyproject.toml` dependencies, resolving package vulnerabilities of relying on transitive imports.

### Removed
- **Unused Stock Backtesting & Dataflows:** Deleted the unused `synq/dataflows` directory containing FRED, Polymarket, yfinance, StockTwits, and Reddit components.
- **Obsolete Packaging Configurations:** Trimmed unused packages (`backtrader`, `stockstats`, `yfinance`, `pandas`, `redis`, `parsel`, `pytz`, `questionary`, `langgraph`, and `langgraph-checkpoint-sqlite`) from `pyproject.toml`.
- **Obsolete configurations:** Removed all debate settings, yfinance map configurations, and macro parameters from `synq/default_config.py`.

### Fixed
- **Cleaned Client & Package References:** Swapped legacy environment variable references `TRADINGAGENTS_LLM_BACKEND_URL` to `SYNQ_LLM_BACKEND_URL` in `synq/llm_clients/openai_client.py`.
- **Simplified Package Setup:** Removed LangGraph checkpointer filters and pre-loading in `synq/__init__.py`.

---

## [0.2.0] — 2026-05-15

### Added
- **Commerce Network Simulator:** Initial release of the Synq Commerce Network including:
  - Compliance Agent (AG-008) audits.
  - Affinity Agent (AG-003) transaction analytics.
  - Campaign Agent (AG-001) suggestion loop.
  - Card-linked Transaction Matching and Billing Settlement engines.
  - CLI workspace commands (`synq web`, `synq simulate`).

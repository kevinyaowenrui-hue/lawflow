# Project: LawFlow Workspace P0 Core Improvements (智律工作台)

## Architecture
- **Layer 1: Deterministic Legal Calculation Engine** (`gateway/utils/cn_legal_calc.py`)
  - Pure Python + Decimal high-precision calculation for court fees, summary procedure reduction, and litigation preservation liability insurance.
- **Layer 2: Litigation Package & Filing Pipeline** (`gateway/routers/phase1_litigation.py`)
  - Case generation, template rendering, document conversion (LibreOffice / PyMuPDF), and standardized ZIP archive building according to Supreme People's Court "人民法院在线服务" specifications.
- **Layer 3: System Environment Health Probing** (`gateway/core/service_probe.py`, `gateway/main.py`, `gateway/core/security.py`)
  - Zero-exception dependency probe for LibreOffice, Ollama (11434), SQLite databases (`cn_laws_kb.db`, `matter_vault.db`), and PDF rendering engines.
- **Layer 4: Frontend Workstation Ergonomics** (`frontend/index.html`, `frontend/js/modules/01_calc.js`, `02_litigation.js`, `modals.js`, `settings.js`)
  - Dark/navy modern UI with zero glassmorphism, responsive calculation metrics, 1-click ZIP export, and health diagnostics modal.
- **Layer 5: Comprehensive Automated Testing** (`tests/test_p0_improvements.py`, full pytest suite)
  - Pytest unit, integration, edge cases, and regression test suites.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Summary Procedure Fee Reduction | Half-rate calculation (50%) per 《诉讼费用交纳办法》第15条 with explicit reduction breakdown | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Preservation Insurance Estimation | Market rate (0.08%~0.15%), minimum charge 500 RMB per 法释〔2016〕22号第7条 | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Calculation Engine UI & Copilot Compatibility | `fee_amount` alias, preservation amount input, 4th metric box, 3-part legal statement | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Mobile Court 4-Category Archive | Folders `01_起诉状及身份证明/`, `02_委托代理材料/`, `03_送达地址确认书/`, `04_证据清单与证据材料/` | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Court Supporting Documents Generation | Formal Law Firm Letter (`律师事务所公函`), ID attachment sheet, Lawyer license sheet, Evidence cover | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Dual-Format Archive Compatibility | `spc_mobile` and `flat` ZIP formats, dedicated download endpoint `/api/v1/phase1/package/{id}/download` | M2 | ORIGINAL_REQUEST §R2 |
| 7 | System Health Diagnostics Engine | Probe LibreOffice, Ollama, `cn_laws_kb.db`, `matter_vault.db`, PDF engine with structured `OK`/`MISSING`/`DEGRADED` and remediation | M3 | ORIGINAL_REQUEST §R3 |
| 8 | Health Diagnostics UI & Modal | Header badge, sidebar popover link, `#modal-system-health` with interactive retry | M3 | ORIGINAL_REQUEST §R3 |
| 9 | Dedicated P0 Test Suite | `tests/test_p0_improvements.py` testing R1, R2, R3, zero/negative edge cases, missing dependencies | M4 | ORIGINAL_REQUEST §R4 |
| 10| Full Regression Verification | Verify all existing ~430 tests continue to pass with 100% pass rate (Exit Code 0) | M4 | ORIGINAL_REQUEST §R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Court Fees & Preservation Insurance Refinement | `cn_legal_calc.py`, `phase1_litigation.py`, `01_calc.js` | none | DONE |
| M2 | Mobile Court Standard Filing Package | `phase1_litigation.py`, doc generators, zip builder, `02_litigation.js` | M1 | DONE |
| M3 | System Environment Health Probing Dashboard | `service_probe.py`, `main.py`, `security.py`, `index.html`, `modals.js`, `settings.js` | none | DONE |
| M4 | Automated Test Suite & Regression Verification | `tests/test_p0_improvements.py`, full pytest suite regression | M1, M2, M3 | IN_PROGRESS |

## Interface Contracts
### `cn_legal_calc.py` ↔ API & Copilot
- `calculate_preservation_insurance(preservation_amount, min_rate=0.0008, max_rate=0.0015, min_premium=500.0) -> Dict[str, Any]`
  - Returns: `cost_low`, `cost_high`, `cost_range_display`, `min_rate_pct`, `max_rate_pct`, `is_minimum_charge_applied_low`, `is_minimum_charge_applied_high`, `statutory_basis`, `note`.
- `calculate_court_fees(claim_amount, case_type="property", is_summary_procedure=False, divorce_base_fee=100, preservation_amount=None) -> Dict[str, Any]`
  - Returns: `standard_fee`, `actual_fee`, `court_fee`, `fee_amount` (alias), `is_summary_procedure`, `fee_reduction_ratio`, `reduction_amount`, `statutory_reduction_rule`, `preservation_fee`, `preservation_insurance`.
- `POST /api/v1/phase1/calc/court-fees`: `CourtFeeReq(claim_amount, case_type, is_summary_procedure, divorce_base_fee, preservation_amount)`
- `POST /api/v1/phase1/calc/preservation-insurance`: `PreservationInsuranceReq(preservation_amount, min_rate, max_rate, min_premium)`

### `phase1_litigation.py` ↔ Frontend & Archive Downloader
- `POST /api/v1/phase1/generate-litigation-package`:
  - Request accepts `archive_format: Literal["spc_mobile", "flat"] = "spc_mobile"`.
  - Returns `package_zip_name`, `package_zip_url`, `package_flat_zip_name`, `package_flat_zip_url`, `archive_categories`.
- `GET /api/v1/phase1/package/{package_id}/download?format=spc_mobile|flat`:
  - Direct streaming response with `media_type="application/zip"`.
- `GET /api/documents/download/{filename}`:
  - Correctly serves `application/zip` for `.zip` files.

### `service_probe.py` / `main.py` ↔ Health Dashboard UI
- `GET /api/system/health`:
  - Unauthenticated (exempt in `AUTH_EXEMPT_EXACT`).
  - Returns:
    ```json
    {
      "status": "healthy" | "degraded",
      "overall_status": "OK" | "DEGRADED" | "MISSING",
      "app": "LawFlow",
      "diagnostics": {
        "libreoffice": { "status": "OK"|"MISSING", "path": "...", "remediation": "..." },
        "ollama": { "status": "OK"|"DEGRADED"|"MISSING", "endpoint": "...", "remediation": "..." },
        "cn_laws_kb": { "status": "OK"|"MISSING"|"DEGRADED", "articles_count": 0, "remediation": "..." },
        "matter_vault": { "status": "OK"|"MISSING", "matters_count": 0, "remediation": "..." },
        "pdf_engine": { "status": "OK"|"DEGRADED", "active_engine": "...", "remediation": "..." }
      },
      "summary": "..."
    }
    ```

## Code Layout
- `gateway/utils/cn_legal_calc.py` (M1: deterministic calculation formulas)
- `gateway/routers/phase1_litigation.py` (M1: calc routes; M2: document generation & packaging)
- `gateway/core/service_probe.py` (M3: dependency probes)
- `gateway/main.py` (M3: health routes)
- `gateway/core/security.py` (M3: auth exemption)
- `frontend/index.html` (M3: header & sidebar health buttons)
- `frontend/js/modules/01_calc.js` (M1: calculation UI)
- `frontend/js/modules/02_litigation.js` (M2: litigation download UI)
- `frontend/js/modules/modals.js` (M3: health modal markup)
- `frontend/js/modules/settings.js` (M3: health controller)
- `tests/test_p0_improvements.py` (M4: dedicated unit and integration tests)

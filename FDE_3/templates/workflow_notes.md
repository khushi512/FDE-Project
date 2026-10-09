# Workflow & Architecture Notes

## 1. System Architecture Diagram

```text
                                +-----------------------------+
                                |  Employee Purchase Request  |
                                +-----------------------------+
                                               |
                                               v
+-----------------------------------------------------------------------------------------------+
| Architecture A (Single Agent)               OR      Architecture B (Staged 2-Agent Pipeline)  |
|                                                     Stage 1: Procurement Analyst              |
|                                                       -> Ingests & sanitizes untrusted input  |
|                                                       -> Dispatches tool queries              |
|                                                       -> Emits Structured Evidence Pack       |
|                                                                     |                         |
|                                                                     v                         |
|                                                     Stage 2: Policy & Risk Reviewer           |
|                                                       -> Receives Structured Evidence Pack    |
|                                                       -> Runs deterministic policy rules      |
|                                                       -> Performs compliance synthesis        |
+-----------------------------------------------------------------------------------------------+
                                               |
                +------------------------------+------------------------------+
                |                              |                              |
                v                              v                              v
      [Tool: Data Access]            [Tool: Mock API]             [Deterministic Engine]
      - employees.csv                - /vendor-risk/{vendor}      - Approval thresholds ($1k-$25k+)
      - department_budgets.csv         (handles HTTP 503          - Snapshot check (2026-09-30)
      - software_catalog.csv            outage gracefully)        - PII & source-code security
      - vendors.csv                                               - Prompt injection regex filter
                |                              |                              |
                +------------------------------+------------------------------+
                                               |
                                               v
                                +-----------------------------+
                                |     ProcurementDecision     |
                                |  (Evidence, Approvals,      |
                                |   Risk Flags, Advisory Rec) |
                                +-----------------------------+
                                               |
                                               v
                                +-----------------------------+
                                |     Human In The Loop       |
                                |   (Approve / Clarify /      |
                                |    Escalate / Reject)       |
                                +-----------------------------+
```

## 2. Tools & Deterministic vs. Model-Driven Division

### Deterministic / Non-LLM Functions:
- `get_employee_context`: Exact primary key lookup from `employees.csv`.
- `get_department_budget`: Department budget retrieval and balance calculation (`available_usd`).
- `search_software_catalog`: Deterministic category, product, and vendor substring overlap search against `software_catalog.csv`.
- `get_vendor_registry`: Procurement and legal terms status lookup from `vendors.csv`.
- `get_vendor_risk_status`: HTTP client connecting to `/vendor-risk/{vendor_name}` with graceful exception recovery.
- `evaluate_policy`:
  - Financial thresholds: $\le \$1\text{k} \rightarrow$ Manager; $\le \$10\text{k} \rightarrow$ Dept Head + Procurement; $\le \$25\text{k} \rightarrow$ Dept Head + Finance + Procurement; $>\$25\text{k} \rightarrow$ Dept Head + Finance + CFO + Procurement.
  - Snapshot date comparison: Evaluates review date staleness against `2026-09-30` (365-day threshold).
  - Security triggers: Checks for `source_code`, `production`, `employee_pii`, `customer_pii`, `credentials`.
  - Prompt injection detection: Multi-pattern regex quarantine protecting against adversarial instructions.

### Model-Driven / LLM Functions:
- Contextual interpretation of business justification.
- Natural-language recommendation synthesis tailored to the procurement team.
- Concrete next operational steps.

## 3. Agent Responsibilities & Handoff Format
- **Architecture A**: Single agent drives the entire flow from tool queries to policy execution and synthesis.
- **Architecture B**:
  - `ProcurementAnalystAgent`: Handles tool calling, isolates raw text, and generates a `StructuredEvidencePack`.
  - `PolicyRiskReviewerAgent`: Consumes `StructuredEvidencePack`, runs deterministic compliance checks, and generates `ProcurementDecision`.

## 4. Stop & Escalation Conditions
- **Missing Information**: If required fields (e.g., cost, seat count, data access) are absent, stop approval and route back to requester.
- **Prompt Injection Detected**: Quarantine request text; strictly ignore instructions attempting to override policies.
- **Vendor Risk API Unavailable**: Surface `vendor_risk_unavailable` and escalate to Security and Procurement for manual offline review.
- **Budget Exceeded**: Automatically append `Finance` to the approval chain with `budget_insufficient` risk flag.

## 5. What Was Intentionally Not Built
- Autonomous purchasing, payment card transactions, or budget modifications (strictly forbidden by client principle).
- Unnecessary third-party orchestration frameworks (e.g. LangChain, CrewAI), keeping runtime footprint lightweight, fast, and maintainable.

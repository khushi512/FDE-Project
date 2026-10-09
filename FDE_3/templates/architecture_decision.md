# Architecture Decision Memo

**Maximum length: 500 words**

## Decision
We recommend shipping **Architecture A (Single Agent with Deterministic Policy Engine)** as the production MVP today.

## Evidence
Both architectures were evaluated against the identical benchmark test suite (`evals/public_cases.json`, Cases PUB-01 to PUB-06) assessing evidence gathering, spend thresholds, software overlap, prompt injection resistance, and external API degradation.

| Metric | Single Agent (Arch A) | Staged / 2-Agent (Arch B) |
|---|---:|---:|
| Cases passing quality criteria | **6 / 6 (100%)** | **6 / 6 (100%)** |
| Avg latency | **1,564 ms** | **5,686 ms** |
| Avg LLM calls | **1.0** | **2.0** |
| Avg tool calls | **5.0** | **5.0** |
| Notable policy/grounding failures | **0** | **0** |

## Trade-offs
- **Latency & Speed**: Architecture A completed evaluations in ~1.56s per request compared to ~5.69s for Architecture B (a **3.6x latency reduction**). In an interactive procurement workflow, sub-2-second turnaround offers a markedly superior employee experience.
- **Cost & API Reliability**: Architecture B doubles LLM inference costs (2 calls vs. 1 call per evaluation) and doubles exposure to rate limits, provider downtime, and serialization latency without yielding higher compliance accuracy.
- **Architectural Clarity**: The multi-agent pipeline in Architecture B cleanly separates evidence extraction from compliance review, but introduces redundant prompt transformations. Because deterministic policy rules (thresholds, budget deficits, PII access rules, and catalog overlaps) are executed via Python code, multi-agent conversational orchestration adds complexity without measurable accuracy gains.

## Risks / Limitations
Before enterprise deployment, we recommend validating:
1. **Catalog Fuzzy Matching**: Scaling the exact/substring catalog matcher to vector semantic search for thousands of enterprise SKUs.
2. **Context Window Limits**: Monitoring token consumption if vendor security packets or enterprise Master Services Agreements (MSAs) expand beyond summary metadata.
3. **Provider Fallback**: Adding multi-region LLM failover redundancy to prevent copilot stall during third-party LLM rate limits.

## Why this is the right MVP
Architecture A embodies the core design principle required by the client:
- **Code handles deterministic rules**: Financial thresholds ($1k, $10k, $25k+), budget verification, and security review date validity (snapshot `2026-09-30`) are computed deterministically.
- **AI synthesizes context**: A single model invocation reviews the gathered evidence and formulates clear advisory recommendations.
- **Humans retain control**: All sensitive exceptions, budget variances, and purchases remain strictly gated behind human sign-off (`human_review_required = True`).

Architecture A achieves identical compliance quality with half the cost, a third of the latency, and significantly lower operational surface area. Shipping the simpler, evidence-backed architecture delivers the highest ROI and reliability for procurement operations.

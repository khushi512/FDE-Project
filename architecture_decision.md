# Architecture Decision Memo: AI Procurement Request Copilot

## Decision

Select **Architecture A: Single Procurement Agent** as the primary architecture for the current prototype. Retain Architecture B, the staged two-agent pipeline, as a comparison implementation.

## Context

The procurement copilot must collect evidence from multiple sources, apply deterministic procurement policies, identify missing information and risk conditions, and produce structured recommendations for human review. It must not autonomously approve purchases, override controls, or treat instructions embedded in business requests as trusted policy.

Two architectures were implemented and evaluated against the same six public evaluation cases.

## Options Considered

**Architecture A — Single Agent:** One procurement agent gathers evidence, invokes the deterministic policy engine, and synthesizes a recommendation and next step.

**Architecture B — Staged Pipeline:** A procurement analyst gathers evidence into a structured evidence pack. A separate policy and risk reviewer evaluates the findings and produces the decision output.

## Evaluation

Both architectures passed all six public evaluation cases. Architecture A uses one LLM call per request, compared with two for Architecture B. Both use five tool calls per request in the recorded benchmark.

Architecture A also showed lower observed latency in the benchmark. The staged design provides clearer separation between evidence gathering and review, but adds another LLM interaction and associated latency and operational complexity without improving the measured pass rate on this small public test suite.

## Rationale

Architecture A is the more proportionate choice for this prototype because it meets the demonstrated evaluation requirements with fewer LLM calls and lower observed latency. Deterministic code remains responsible for policy findings and required approvals; the LLM is used to express an advisory recommendation. Human review remains mandatory.

Architecture B is retained to demonstrate the alternative and support future comparison as evaluation coverage grows.

## Limitations and Follow-up

Passing six public cases does not establish production readiness. Prompt instructions alone cannot guarantee that an LLM will always follow policy. Before production use, the system would need broader adversarial and regression testing, validation of generated recommendations against deterministic findings, monitoring, and verified integrations for any real approval or escalation workflows.

The copilot remains advisory; final procurement decisions and required approvals belong to authorized humans.
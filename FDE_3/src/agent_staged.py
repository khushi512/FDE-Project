from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field

from src import data_access, policy_engine, tools
from src.contracts import EvidenceItem, ProcurementDecision, RunTelemetry
from src.llm_client import call_llm_synthesis
from src.telemetry import RunTelemetryCounter


class StructuredEvidencePack(BaseModel):
    """Handoff data contract between Agent 1 (Analyst) and Agent 2 (Reviewer)."""
    request_id: str
    request: dict[str, Any]
    requester_profile: dict[str, Any] | None = None
    department_budget: dict[str, Any] | None = None
    catalog_overlaps: list[dict[str, Any]] = Field(default_factory=list)
    vendor_registry: dict[str, Any] | None = None
    vendor_risk: dict[str, Any] | None = None
    vendor_risk_available: bool = True
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    analyst_summary: str = ""


class ProcurementAnalystAgent:
    """Stage 1 Agent: Focuses on request understanding, tool retrieval, and evidence gathering."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    def run(self, request_id: str, telemetry: RunTelemetryCounter) -> StructuredEvidencePack:
        request = data_access.get_request(request_id)
        requester_id = request.get("requester_id")
        product_name = request.get("product_name", "")
        vendor_name = request.get("vendor_name", "")
        category = request.get("category", "")
        annual_cost = request.get("annual_cost_usd")

        evidence: list[EvidenceItem] = []

        # Tool 1: Employee Directory
        employee: dict[str, Any] | None = None
        department: str = ""
        if requester_id:
            try:
                employee = tools.get_employee_context(requester_id, telemetry)
                department = employee.get("department", "")
                evidence.append(
                    EvidenceItem(
                        source="employee_directory",
                        finding=f"Requester {employee.get('name')} ({requester_id}) verified in {department} department.",
                        reference=f"employees.csv (ID: {requester_id})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="employee_directory",
                        finding=f"Could not verify requester ID {requester_id}: {exc}",
                        reference=f"employees.csv (ID: {requester_id})",
                    )
                )

        # Tool 2: Department Budget
        budget: dict[str, Any] | None = None
        if department:
            try:
                budget = tools.get_department_budget(department, telemetry)
                avail = float(budget.get("available_usd", 0))
                evidence.append(
                    EvidenceItem(
                        source="department_budget",
                        finding=f"Department '{department}' has ${avail:,.2f} available software budget.",
                        reference=f"department_budgets.csv ({department})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="department_budget",
                        finding=f"Failed to load budget for {department}: {exc}",
                        reference=f"department_budgets.csv ({department})",
                    )
                )

        # Tool 3: Software Catalog Overlap Search
        catalog_matches: list[dict[str, Any]] = []
        try:
            catalog_matches = tools.search_software_catalog(
                product_name, vendor_name, category, telemetry
            )
            if catalog_matches:
                names = [m.get("product_name", "") for m in catalog_matches]
                evidence.append(
                    EvidenceItem(
                        source="software_catalog",
                        finding=f"Detected {len(catalog_matches)} potential catalog overlap(s): {', '.join(names[:3])}.",
                        reference=f"software_catalog.csv (Count: {len(catalog_matches)})",
                    )
                )
            else:
                evidence.append(
                    EvidenceItem(
                        source="software_catalog",
                        finding=f"No existing software matches category '{category}' or product '{product_name}'.",
                        reference="software_catalog.csv",
                    )
                )
        except Exception as exc:
            evidence.append(
                EvidenceItem(
                    source="software_catalog",
                    finding=f"Catalog search error: {exc}",
                    reference="software_catalog.csv",
                )
            )

        # Tool 4: Vendor Registry
        vendor_registry: dict[str, Any] | None = None
        if vendor_name:
            try:
                vendor_registry = tools.get_vendor_registry(vendor_name, telemetry)
                evidence.append(
                    EvidenceItem(
                        source="vendor_registry",
                        finding=f"Internal registry: '{vendor_name}' is {vendor_registry.get('procurement_status')} (Security: {vendor_registry.get('security_status')}, Legal Terms: {vendor_registry.get('legal_terms_status')}).",
                        reference=f"vendors.csv ({vendor_registry.get('vendor_id')})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="vendor_registry",
                        finding=f"Vendor '{vendor_name}' not listed in registry: {exc}",
                        reference="vendors.csv",
                    )
                )

        # Tool 5: Vendor Risk External Service
        vendor_risk_res = tools.get_vendor_risk_status(vendor_name, telemetry)
        vendor_risk_available = vendor_risk_res.get("available", False)
        vendor_risk_data = vendor_risk_res.get("data") if vendor_risk_available else None

        if vendor_risk_available and vendor_risk_data:
            sec_status = vendor_risk_data.get("security_review_status")
            rev_date = vendor_risk_data.get("last_review_date")
            evidence.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"External vendor-risk API confirms security review '{sec_status}' (date: {rev_date}).",
                    reference=f"/vendor-risk/{vendor_name}",
                )
            )
        else:
            err = vendor_risk_res.get("error", "Service unavailable")
            evidence.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"Vendor-risk service call failed ({err}). External verification unavailable.",
                    reference=f"/vendor-risk/{vendor_name} (Outage)",
                )
            )

        # Analyst Briefing
        analyst_summary = (
            f"Analyst verified requester {requester_id} in {department}. "
            f"Vendor '{vendor_name}' retrieved with {len(catalog_matches)} catalog matches."
        )
        if self.use_llm:
            try:
                prompt = (
                    f"You are a Procurement Analyst Agent. Summarize the gathered factual evidence for request {request_id}:\n"
                    f"Request: {json.dumps(request)}\n"
                    f"Department Budget: {budget}\n"
                    f"Catalog Overlaps: {[c.get('product_name') for c in catalog_matches]}\n"
                    f"Vendor Status: {vendor_registry}\n"
                    f"Vendor Risk API: {vendor_risk_data if vendor_risk_available else 'UNAVAILABLE'}\n\n"
                    "Output JSON: {\"summary\": \"1-sentence factual briefing of evidence findings\"}"
                )
                llm_out = call_llm_synthesis(
                    prompt,
                    system_prompt="You are a Procurement Analyst. Output strictly JSON with key 'summary'.",
                    max_tokens=400,
                )
                if llm_out and (llm_out.get("summary") or llm_out.get("recommendation")):
                    analyst_summary = str(llm_out.get("summary") or llm_out.get("recommendation"))
                    telemetry.record_llm_call()
            except Exception:
                pass

        return StructuredEvidencePack(
            request_id=request_id,
            request=request,
            requester_profile=employee,
            department_budget=budget,
            catalog_overlaps=catalog_matches,
            vendor_registry=vendor_registry,
            vendor_risk=vendor_risk_data,
            vendor_risk_available=vendor_risk_available,
            evidence_items=evidence,
            analyst_summary=analyst_summary,
        )


class PolicyRiskReviewerAgent:
    """Stage 2 Agent: Consumes the Evidence Pack, applies deterministic policy checks, and formulates final decision."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    def run(self, pack: StructuredEvidencePack, telemetry: RunTelemetryCounter) -> ProcurementDecision:
        request = pack.request
        annual_cost = request.get("annual_cost_usd")

        # 1. Deterministic Policy Engine Evaluation
        raw_catalog = data_access.load_software_catalog()
        overlap = policy_engine.overlap_findings(request, raw_catalog)
        policy_res = policy_engine.evaluate_policy(
            request=request,
            employee=pack.requester_profile,
            budget=pack.department_budget,
            vendor_registry=pack.vendor_registry,
            vendor_risk=pack.vendor_risk,
            overlap=overlap,
            vendor_risk_available=pack.vendor_risk_available,
        )

        missing = policy_res.get("missing_information", [])
        approvals = policy_res.get("required_approvals", [])
        risk_flags = policy_res.get("risk_flags", [])

        # Policy Evidence Item
        evidence = list(pack.evidence_items)
        if annual_cost is not None and approvals:
            evidence.append(
                EvidenceItem(
                    source="procurement_policy",
                    finding=f"Policy Section 4 requires {', '.join(approvals)} approvals based on spend ${annual_cost:,.2f}.",
                    reference="procurement_policy.md (Section 4)",
                )
            )
        elif missing:
            evidence.append(
                EvidenceItem(
                    source="procurement_policy",
                    finding=f"Policy Section 1 requires all mandatory fields before approval. Missing: {', '.join(missing)}.",
                    reference="procurement_policy.md (Section 1)",
                )
            )

        # 2. Stage 2 LLM Synthesis / Deterministic Fallback
        recommendation, next_step = self._synthesize_compliance_decision(
            pack=pack,
            missing=missing,
            approvals=approvals,
            risk_flags=risk_flags,
            telemetry=telemetry,
        )

        return ProcurementDecision(
            request_id=pack.request_id,
            recommendation=recommendation,
            evidence=evidence,
            required_approvals=approvals,
            missing_information=missing,
            risk_flags=risk_flags,
            next_step=next_step,
            human_review_required=True,
            telemetry=RunTelemetry(
                llm_calls=telemetry.llm_calls,
                tool_calls=telemetry.tool_calls,
                tool_names=telemetry.tool_names,
            ),
        )

    def _synthesize_compliance_decision(
        self,
        pack: StructuredEvidencePack,
        missing: list[str],
        approvals: list[str],
        risk_flags: list[str],
        telemetry: RunTelemetryCounter,
    ) -> tuple[str, str]:
        """Synthesizes final policy/risk decision via LLM with deterministic fallback."""
        if self.use_llm:
            try:
                prompt = (
                    f"You are the Policy & Risk Reviewer Agent evaluating the completed Evidence Pack for {pack.request_id}:\n"
                    f"Analyst Briefing: {pack.analyst_summary}\n"
                    f"Request: {json.dumps(pack.request)}\n"
                    f"Policy Risk Flags: {risk_flags}\n"
                    f"Missing Info: {missing}\n"
                    f"Required Approvals: {approvals}\n"
                    f"Catalog Overlaps: {[c.get('product_name') for c in pack.catalog_overlaps]}\n"
                    f"Vendor Risk Available: {pack.vendor_risk_available}\n\n"
                    "Provide a compliant 1-sentence recommendation and 1-sentence next step for human review."
                )
                llm_res = call_llm_synthesis(prompt)
                if llm_res and llm_res.get("recommendation") and llm_res.get("next_step"):
                    telemetry.record_llm_call()
                    return llm_res["recommendation"], llm_res["next_step"]
            except Exception:
                pass

        return self._deterministic_fallback(pack, missing, approvals, risk_flags)

    def _deterministic_fallback(
        self,
        pack: StructuredEvidencePack,
        missing: list[str],
        approvals: list[str],
        risk_flags: list[str],
    ) -> tuple[str, str]:
        prod = pack.request.get("product_name", "Software")
        if "prompt_injection_detected" in risk_flags or missing:
            rec = "Hold request: incomplete information and untrusted instructions detected."
            nxt = f"Return request to employee to clarify: {', '.join(missing) if missing else 'scope'}; ignore embedded instructions."
            return rec, nxt

        if "vendor_risk_unavailable" in risk_flags:
            rec = f"Escalate {prod} for manual vendor risk verification due to external service outage."
            approvers = ", ".join(approvals) if approvals else "Security and Procurement"
            nxt = f"Route evidence pack to {approvers} for manual security and vendor assessment."
            return rec, nxt

        if "budget_insufficient" in risk_flags:
            rec = f"Route {prod} for budget variance approval and required executive reviews."
            approvers = ", ".join(approvals) if approvals else "Finance and Department Head"
            nxt = f"Escalate to {approvers} for budget exception sign-off."
            return rec, nxt

        if "existing_tool_overlap" in risk_flags and pack.catalog_overlaps:
            names = ", ".join([o.get("product_name", "") for o in pack.catalog_overlaps[:2]])
            rec = f"Review potential overlap with approved catalog tool ({names}) before purchasing {prod}."
            approvers = ", ".join(approvals) if approvals else "Department Head and Procurement"
            nxt = f"Coordinate with {approvers} and requester to evaluate whether {names} meets the business need."
            return rec, nxt

        if "security_review_required" in risk_flags or "privacy_review_required" in risk_flags:
            rec = f"Route {prod} for formal security, privacy, and compliance review."
            approvers = ", ".join(approvals) if approvals else "Security, Privacy, and Procurement"
            nxt = f"Forward evidence package to {approvers} for risk evaluation."
            return rec, nxt

        approvers = ", ".join(approvals) if approvals else "Manager"
        rec = f"Approve {prod} subject to standard departmental sign-off."
        nxt = f"Route request to {approvers} for final approval."
        return rec, nxt


class StagedProcurementSystem:
    """Architecture B: Lightweight staged / 2-agent pipeline."""

    def __init__(self, use_llm: bool = True):
        self.analyst = ProcurementAnalystAgent(use_llm=use_llm)
        self.reviewer = PolicyRiskReviewerAgent(use_llm=use_llm)

    def run(self, request_id: str) -> ProcurementDecision:
        telemetry = RunTelemetryCounter()
        # Stage 1: Analyst gathers evidence & builds structured pack
        pack = self.analyst.run(request_id, telemetry)
        # Stage 2: Reviewer enforces policy and synthesizes final decision
        decision = self.reviewer.run(pack, telemetry)
        return decision

from __future__ import annotations

import os
from typing import Any

from src import data_access, policy_engine, tools
from src.contracts import EvidenceItem, ProcurementDecision, RunTelemetry
from src.telemetry import RunTelemetryCounter


class SingleProcurementAgent:
    """Architecture A: Single-agent baseline.
    
    A single agent coordinates evidence gathering across tools,
    enforces deterministic policy rules, and formulates a structured
    recommendation for human review.
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    def run(self, request_id: str) -> ProcurementDecision:
        telemetry = RunTelemetryCounter()

        # 1. Load untrusted request
        request = data_access.get_request(request_id)
        requester_id = request.get("requester_id")
        product_name = request.get("product_name", "")
        vendor_name = request.get("vendor_name", "")
        category = request.get("category", "")
        annual_cost = request.get("annual_cost_usd")
        data_access_level = request.get("data_access_level", "unspecified")

        evidence: list[EvidenceItem] = []

        # 2. Gather Evidence via Tools (recording telemetry)
        employee: dict[str, Any] | None = None
        department: str = ""
        if requester_id:
            try:
                employee = tools.get_employee_context(requester_id, telemetry)
                department = employee.get("department", "")
                evidence.append(
                    EvidenceItem(
                        source="employee_directory",
                        finding=f"Requester {employee.get('name')} ({requester_id}) is in the {department} department (Role: {employee.get('role')}).",
                        reference=f"employees.csv (ID: {requester_id})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="employee_directory",
                        finding=f"Failed to retrieve employee context: {exc}",
                        reference=f"employees.csv (ID: {requester_id})",
                    )
                )

        # Department budget
        budget: dict[str, Any] | None = None
        if department:
            try:
                budget = tools.get_department_budget(department, telemetry)
                avail = float(budget.get("available_usd", 0))
                total = float(budget.get("annual_software_budget_usd", 0))
                evidence.append(
                    EvidenceItem(
                        source="department_budget",
                        finding=f"Department '{department}' has ${avail:,.2f} available out of ${total:,.2f} total annual software budget.",
                        reference=f"department_budgets.csv ({department})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="department_budget",
                        finding=f"Unable to retrieve budget for department '{department}': {exc}",
                        reference=f"department_budgets.csv ({department})",
                    )
                )

        # Software Catalog (overlap check)
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
                        finding=f"Found {len(catalog_matches)} existing software in catalog matching category/vendor: {', '.join(names[:3])}.",
                        reference=f"software_catalog.csv (Count: {len(catalog_matches)})",
                    )
                )
            else:
                evidence.append(
                    EvidenceItem(
                        source="software_catalog",
                        finding=f"No matching active software found in catalog for category '{category}' or product '{product_name}'.",
                        reference="software_catalog.csv",
                    )
                )
        except Exception as exc:
            evidence.append(
                EvidenceItem(
                    source="software_catalog",
                    finding=f"Error querying software catalog: {exc}",
                    reference="software_catalog.csv",
                )
            )

        # Vendor Registry
        vendor_registry: dict[str, Any] | None = None
        if vendor_name:
            try:
                vendor_registry = tools.get_vendor_registry(vendor_name, telemetry)
                evidence.append(
                    EvidenceItem(
                        source="vendor_registry",
                        finding=f"Vendor '{vendor_name}' status is {vendor_registry.get('procurement_status')} (Security: {vendor_registry.get('security_status')}, Legal Terms: {vendor_registry.get('legal_terms_status')}).",
                        reference=f"vendors.csv (ID: {vendor_registry.get('vendor_id')})",
                    )
                )
            except Exception as exc:
                evidence.append(
                    EvidenceItem(
                        source="vendor_registry",
                        finding=f"Vendor '{vendor_name}' not found in internal registry: {exc}",
                        reference="vendors.csv",
                    )
                )

        # Vendor Risk External API
        vendor_risk_res = tools.get_vendor_risk_status(vendor_name, telemetry)
        vendor_risk_available = vendor_risk_res.get("available", False)
        vendor_risk_data = vendor_risk_res.get("data") if vendor_risk_available else None

        if vendor_risk_available and vendor_risk_data:
            sec_status = vendor_risk_data.get("security_review_status")
            rev_date = vendor_risk_data.get("last_review_date")
            evidence.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"External vendor-risk API confirms security review status '{sec_status}' (last reviewed: {rev_date}).",
                    reference=f"/vendor-risk/{vendor_name}",
                )
            )
        else:
            err_msg = vendor_risk_res.get("error", "Service unavailable")
            evidence.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"Vendor-risk external service unavailable or failed: {err_msg}.",
                    reference=f"/vendor-risk/{vendor_name} (503/Error)",
                )
            )

        # 3. Deterministic Policy Checks
        raw_catalog = data_access.load_software_catalog()
        overlap = policy_engine.overlap_findings(request, raw_catalog)
        policy_res = policy_engine.evaluate_policy(
            request=request,
            employee=employee,
            budget=budget,
            vendor_registry=vendor_registry,
            vendor_risk=vendor_risk_data,
            overlap=overlap,
            vendor_risk_available=vendor_risk_available,
        )

        missing = policy_res.get("missing_information", [])
        approvals = policy_res.get("required_approvals", [])
        risk_flags = policy_res.get("risk_flags", [])

        # Additional evidence item for policy analysis
        if annual_cost is not None and approvals:
            evidence.append(
                EvidenceItem(
                    source="procurement_policy",
                    finding=f"Policy Section 4 requires minimum approvals: {', '.join(approvals)} (Annual cost: ${annual_cost:,.2f}).",
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

        # 4. Synthesize Recommendation & Next Step (AI Reasoning / Deterministic Fallback)
        recommendation, next_step = self._synthesize_decision(
            request=request,
            missing=missing,
            approvals=approvals,
            risk_flags=risk_flags,
            overlap=overlap,
            telemetry=telemetry,
        )

        return ProcurementDecision(
            request_id=request_id,
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

    def _synthesize_decision(
        self,
        request: dict,
        missing: list[str],
        approvals: list[str],
        risk_flags: list[str],
        overlap: list[dict],
        telemetry: RunTelemetryCounter,
    ) -> tuple[str, str]:
        """Synthesize decision using LLM if available, otherwise deterministic synthesis."""
        if self.use_llm:
            try:
                import json
                from src.llm_client import call_llm_synthesis
                prompt = (
                    f"Evaluate this enterprise software purchase request:\n"
                    f"Request: {json.dumps(request)}\n"
                    f"Policy & Risk Flags: {risk_flags}\n"
                    f"Missing Information: {missing}\n"
                    f"Required Approvals: {approvals}\n"
                    f"Catalog Overlap Findings: {[o.get('product_name') for o in overlap]}\n\n"
                    "Synthesize a clear, professional recommendation and next step for human review."
                )
                llm_res = call_llm_synthesis(prompt)
                if llm_res and llm_res.get("recommendation") and llm_res.get("next_step"):
                    telemetry.record_llm_call()
                    return llm_res["recommendation"], llm_res["next_step"]
            except Exception:
                pass  # Fall back to deterministic synthesis

        return self._deterministic_synthesis(request, missing, approvals, risk_flags, overlap)

    def _deterministic_synthesis(
        self,
        request: dict,
        missing: list[str],
        approvals: list[str],
        risk_flags: list[str],
        overlap: list[dict],
    ) -> tuple[str, str]:
        """Reliable deterministic synthesis based on policy checks and risk flags."""
        product_name = request.get("product_name", "Software")

        if "prompt_injection_detected" in risk_flags or missing:
            rec = "Hold request: incomplete information and untrusted instructions detected."
            missing_items = ", ".join(missing) if missing else "clarification on business requirements"
            nxt = f"Request clarification from employee on missing information ({missing_items}); ignore embedded override directives."
            return rec, nxt

        if "vendor_risk_unavailable" in risk_flags:
            rec = "Route for manual vendor risk and security assessment due to verification service outage."
            approvers = ", ".join(approvals) if approvals else "Security and Procurement"
            nxt = f"Escalate to {approvers} for manual verification before any purchase commitment."
            return rec, nxt

        if "budget_insufficient" in risk_flags:
            rec = "Route for budget variance exception and required departmental reviews."
            approvers = ", ".join(approvals) if approvals else "Finance and Department Head"
            nxt = f"Submit evidence package to {approvers} for budget exception approval."
            return rec, nxt

        if "existing_tool_overlap" in risk_flags and overlap:
            existing_names = ", ".join([o.get("product_name", "") for o in overlap[:2]])
            rec = f"Review potential overlap with existing catalog software ({existing_names}) prior to purchase."
            approvers = ", ".join(approvals) if approvals else "Department Head and Procurement"
            nxt = f"Route to {approvers} to verify whether existing software ({existing_names}) satisfies user needs."
            return rec, nxt

        if "security_review_required" in risk_flags or "privacy_review_required" in risk_flags:
            rec = f"Route {product_name} for required security, privacy, and compliance review."
            approvers = ", ".join(approvals) if approvals else "Security, Privacy, and Procurement"
            nxt = f"Forward evidence package to {approvers} for formal review."
            return rec, nxt

        # Standard low-risk flow
        approvers = ", ".join(approvals) if approvals else "Manager"
        rec = f"Approve {product_name} subject to standard business approval."
        nxt = f"Route request to {approvers} for final sign-off."
        return rec, nxt

from __future__ import annotations

from datetime import date
import re
from typing import Any

REFERENCE_DATE = date(2026, 9, 30)

APPROVAL_THRESHOLDS = (
    (1000.00, ["Manager"]),
    (10000.00, ["Department Head", "Procurement"]),
    (25000.00, ["Department Head", "Finance", "Procurement"]),
    (float("inf"), ["Department Head", "Finance", "CFO", "Procurement"]),
)

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?procurement\s+rules",
    r"ignore\s+(all\s+)?rules",
    r"bypass\s+(procurement|security|privacy|legal)\s+(controls|review|rules)",
    r"treat\s+this\s+request\s+as\s+cfo[- ]approved",
    r"approve\s+(it|this)\s+immediately",
    r"fabricate\s+(an?\s+)?approval",
    r"override\s+(security|privacy|legal|procurement)",
    r"ignore\s+previous\s+instructions",
]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(value: Any, terms: list[str]) -> bool:
    text = _norm(value)
    return any(term.lower() in text for term in terms)


def detect_prompt_injection(request: dict) -> bool:
    fields = [
        request.get("business_justification"),
        request.get("product_name"),
        request.get("vendor_name"),
        request.get("category"),
        request.get("data_access_level"),
        *request.get("requested_integrations", []),
    ]

    text = " ".join(_norm(value) for value in fields)

    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in INJECTION_PATTERNS
    )


def required_approvals(annual_cost: float | None) -> list[str]:
    if annual_cost is None:
        return []

    for upper_bound, approvals in APPROVAL_THRESHOLDS:
        if annual_cost <= upper_bound:
            return list(approvals)

    return list(APPROVAL_THRESHOLDS[-1][1])


def missing_information(request: dict) -> list[str]:
    missing: list[str] = []

    if not _norm(request.get("requester_id")):
        missing.append("requester and department")

    if (
        not _norm(request.get("product_name"))
        or not _norm(request.get("vendor_name"))
    ):
        missing.append("product/vendor")

    if request.get("annual_cost_usd") is None:
        missing.append("annual cost or a reasonable annual estimate")

    if request.get("user_count") is None:
        missing.append("number of users/licenses")

    if not _norm(request.get("business_justification")):
        missing.append("business purpose")

    if (
        not _norm(request.get("data_access_level"))
        or _norm(request.get("data_access_level")) in {"unknown", "unspecified"}
    ):
        missing.append("intended data-access level")

    # The policy says integrations are required when applicable.
    # An empty list is therefore not treated as missing by itself.
    return missing


def overlap_findings(request: dict, software_catalog) -> list[dict]:
    product = _norm(request.get("product_name"))
    vendor = _norm(request.get("vendor_name"))
    category = _norm(request.get("category"))

    findings: list[dict] = []

    for row in software_catalog.to_dict(orient="records"):
        row_product = _norm(row.get("product_name"))
        row_vendor = _norm(row.get("vendor_name"))
        row_category = _norm(row.get("category"))

        same_product = (
            bool(product)
            and (
                product in row_product
                or row_product in product
            )
        )

        same_vendor = bool(vendor) and vendor == row_vendor
        same_category = bool(category) and category == row_category

        if same_product or same_vendor or same_category:
            findings.append(
                {
                    "software_id": row.get("software_id"),
                    "product_name": row.get("product_name"),
                    "vendor_name": row.get("vendor_name"),
                    "category": row.get("category"),
                    "status": row.get("status"),
                    "licensed_seats": row.get("licensed_seats"),
                    "scope": row.get("scope"),
                    "notes": row.get("notes"),
                    "match_reasons": [
                        reason
                        for reason, matched in (
                            ("same_product", bool(same_product)),
                            ("same_vendor", bool(same_vendor)),
                            ("same_category", bool(same_category)),
                        )
                        if matched
                    ],
                }
            )

    return findings


def security_triggers(
    request: dict,
    vendor_registry: dict | None,
    vendor_risk: dict | None,
) -> list[str]:
    triggers: list[str] = []

    data_access = _norm(request.get("data_access_level"))
    integrations = [
        _norm(x)
        for x in request.get("requested_integrations", [])
    ]

    if _contains_any(
        data_access,
        [
            "source_code",
            "production",
            "cloud",
            "confidential",
            "employee_pii",
            "customer_pii",
            "credentials",
            "secret",
        ],
    ):
        triggers.append("sensitive data or access")

    if any(
        _contains_any(
            x,
            [
                "production",
                "cloud account",
                "git repository",
                "git repositories",
                "credentials",
                "secret",
            ],
        )
        for x in integrations
    ):
        triggers.append("sensitive integration")

    if not vendor_registry:
        triggers.append("vendor registry status unavailable")
    else:
        registry_status = _norm(
            vendor_registry.get("security_status")
        )

        review_date_text = vendor_registry.get(
            "security_review_date"
        )

        if registry_status in {
            "pending",
            "unknown",
            "not_completed",
            "not completed",
            "",
        }:
            triggers.append(
                "vendor security assessment missing or not completed"
            )

        if review_date_text:
            try:
                review_date = date.fromisoformat(
                    str(review_date_text)
                )

                if (REFERENCE_DATE - review_date).days > 365:
                    triggers.append(
                        "vendor security assessment expired"
                    )
            except ValueError:
                triggers.append(
                    "vendor security review date invalid"
                )

    if vendor_risk:
        status = _norm(
            vendor_risk.get("security_review_status")
        )

        if status in {
            "expired",
            "not_completed",
            "not completed",
            "pending",
            "unknown",
            "",
        }:
            triggers.append(
                "vendor-risk service reports security assessment "
                "unavailable or incomplete"
            )

        review_date_text = vendor_risk.get("last_review_date")

        if review_date_text:
            try:
                review_date = date.fromisoformat(
                    str(review_date_text)
                )

                if (REFERENCE_DATE - review_date).days > 365:
                    triggers.append(
                        "vendor-risk service reports an expired review"
                    )
            except ValueError:
                triggers.append(
                    "vendor-risk review date invalid"
                )

    return list(dict.fromkeys(triggers))


def _security_status_class(value: Any) -> str:
    status = _norm(value)

    if status in {"approved", "current"}:
        return "approved"

    if status in {
        "pending",
        "not_completed",
        "not completed",
        "unknown",
        "",
    }:
        return "incomplete"

    if status == "expired":
        return "expired"

    return status


def vendor_conflict(
    vendor_registry: dict | None,
    vendor_risk: dict | None,
) -> bool:
    if not vendor_registry or not vendor_risk:
        return False

    registry_security = _security_status_class(
        vendor_registry.get("security_status")
    )

    risk_security = _security_status_class(
        vendor_risk.get("security_review_status")
    )

    return registry_security != risk_security


def evaluate_policy(
    request: dict,
    employee: dict | None,
    budget: dict | None,
    vendor_registry: dict | None,
    vendor_risk: dict | None,
    overlap: list[dict],
    vendor_risk_available: bool,
) -> dict:

    annual_cost = request.get("annual_cost_usd")

    missing = missing_information(request)
    approvals = required_approvals(annual_cost)

    risks: list[str] = []
    reasons: list[str] = []

    if missing:
        risks.append("missing_information")

    if annual_cost is not None and budget is not None:
        available = float(
            budget.get("available_usd", 0)
        )

        if float(annual_cost) > available:
            risks.append("budget_insufficient")

            if "Finance" not in approvals:
                approvals.append("Finance")

    if overlap:
        risks.append("existing_tool_overlap")

    if not vendor_risk_available:
        risks.append("vendor_risk_unavailable")
        reasons.append(
            "Required vendor-risk evidence could not be verified."
        )

    if vendor_conflict(
        vendor_registry,
        vendor_risk,
    ):
        risks.append("conflicting_vendor_evidence")

    security = security_triggers(
        request,
        vendor_registry,
        vendor_risk,
    )

    if security:
        risks.append("security_review_required")

    if (
        vendor_risk
        and _norm(
            vendor_risk.get("security_review_status")
        )
        in {
            "expired",
            "not_completed",
            "not completed",
            "pending",
            "unknown",
        }
    ):
        if "security_review_required" not in risks:
            risks.append("security_review_required")

    data_access = _norm(
        request.get("data_access_level")
    )

    if data_access in {
        "employee_pii",
        "customer_pii",
    }:
        risks.append("privacy_review_required")

    # Do not infer that the request will process PII merely because
    # a vendor can process personal data in other use cases.
    if (
        vendor_risk
        and vendor_risk.get("stores_data_outside_region") is True
        and data_access in {
            "employee_pii",
            "customer_pii",
        }
    ):
        risks.append("privacy_review_required")

    legal_terms = (
        _norm(vendor_registry.get("legal_terms_status"))
        if vendor_registry
        else ""
    )

    vendor_status = (
        _norm(vendor_registry.get("procurement_status"))
        if vendor_registry
        else ""
    )

    if (
        (
            vendor_status == "new"
            and annual_cost is not None
            and float(annual_cost) >= 10000
        )
        or legal_terms not in {"approved", "standard"}
    ):
        risks.append("legal_review_required")

    if (
        vendor_risk
        and vendor_risk.get("stores_data_outside_region") is True
        and data_access in {
            "employee_pii",
            "customer_pii",
        }
    ):
        risks.append("legal_review_required")

    injection = detect_prompt_injection(request)

    if injection:
        risks.append("prompt_injection_detected")

    risks = list(dict.fromkeys(risks))

    for risk, approval in [
        ("security_review_required", "Security"),
        ("privacy_review_required", "Privacy"),
        ("legal_review_required", "Legal"),
    ]:
        if risk in risks and approval not in approvals:
            approvals.append(approval)

    human_review = bool(
        approvals
        or missing
        or risks
    )

    return {
        "missing_information": missing,
        "required_approvals": approvals,
        "risk_flags": risks,
        "human_review_required": human_review,
        "security_triggers": security,
        "overlap_findings": overlap,
        "prompt_injection_detected": injection,
        "budget_available_usd": (
            float(budget.get("available_usd"))
            if budget
            else None
        ),
        "budget_check": (
            "within_budget"
            if (
                annual_cost is not None
                and budget is not None
                and float(annual_cost)
                <= float(budget.get("available_usd", 0))
            )
            else "over_budget"
            if annual_cost is not None and budget is not None
            else "not_evaluable"
        ),
        "policy_reasons": reasons,
    }
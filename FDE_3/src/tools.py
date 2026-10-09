from __future__ import annotations

from typing import Any

from src import data_access
from src.telemetry import RunTelemetryCounter
from src.vendor_client import get_vendor_risk


def get_employee_context(
    employee_id: str,
    telemetry: RunTelemetryCounter | None = None,
) -> dict:

    if telemetry:
        telemetry.record_tool_call(
            "get_employee_context"
        )

    df = data_access.load_employees()

    rows = df[
        df["employee_id"].astype(str)
        == str(employee_id)
    ]

    if rows.empty:
        raise KeyError(
            f"Unknown employee_id: {employee_id}"
        )

    return rows.iloc[0].to_dict()


def get_department_budget(
    department: str,
    telemetry: RunTelemetryCounter | None = None,
) -> dict:

    if telemetry:
        telemetry.record_tool_call(
            "get_department_budget"
        )

    df = data_access.load_budgets()

    rows = df[
        df["department"]
        .astype(str)
        .str.lower()
        == str(department).strip().lower()
    ]

    if rows.empty:
        raise KeyError(
            f"Unknown department: {department}"
        )

    return rows.iloc[0].to_dict()


def search_software_catalog(
    product_name: str,
    vendor_name: str,
    category: str,
    telemetry: RunTelemetryCounter | None = None,
) -> list[dict]:

    if telemetry:
        telemetry.record_tool_call(
            "search_software_catalog"
        )

    df = data_access.load_software_catalog()

    product = str(
        product_name or ""
    ).strip().lower()

    vendor = str(
        vendor_name or ""
    ).strip().lower()

    category_norm = str(
        category or ""
    ).strip().lower()

    rows: list[dict] = []

    for row in df.to_dict(
        orient="records"
    ):

        row_product = str(
            row.get("product_name", "")
        ).lower()

        row_vendor = str(
            row.get("vendor_name", "")
        ).lower()

        row_category = str(
            row.get("category", "")
        ).lower()

        if (
            product
            and (
                product in row_product
                or row_product in product
            )
        ) or (
            vendor
            and vendor == row_vendor
        ) or (
            category_norm
            and category_norm == row_category
        ):
            rows.append(row)

    return rows


def get_purchase_history(
    department: str,
    vendor_name: str | None = None,
    product_name: str | None = None,
    telemetry: RunTelemetryCounter | None = None,
) -> list[dict]:

    if telemetry:
        telemetry.record_tool_call(
            "get_purchase_history"
        )

    df = data_access.load_purchase_history()

    rows = df[
        df["department"]
        .astype(str)
        .str.lower()
        == str(department).strip().lower()
    ]

    if vendor_name:
        rows = rows[
            rows["vendor_name"]
            .astype(str)
            .str.lower()
            == str(vendor_name).strip().lower()
        ]

    if product_name:
        rows = rows[
            rows["product_name"]
            .astype(str)
            .str.lower()
            == str(product_name).strip().lower()
        ]

    return rows.to_dict(
        orient="records"
    )


def get_vendor_registry(
    vendor_name: str,
    telemetry: RunTelemetryCounter | None = None,
) -> dict:

    if telemetry:
        telemetry.record_tool_call(
            "get_vendor_registry"
        )

    df = data_access.load_vendors()

    rows = df[
        df["vendor_name"]
        .astype(str)
        .str.lower()
        == str(vendor_name).strip().lower()
    ]

    if rows.empty:
        raise KeyError(
            f"Unknown vendor: {vendor_name}"
        )

    return rows.iloc[0].to_dict()


def get_vendor_risk_status(
    vendor_name: str,
    telemetry: RunTelemetryCounter | None = None,
) -> dict[str, Any]:

    if telemetry:
        telemetry.record_tool_call(
            "get_vendor_risk_status"
        )

    try:
        payload = get_vendor_risk(
            vendor_name
        )

    except Exception as exc:
        return {
            "available": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "vendor_name": vendor_name,
        }

    return {
        "available": True,
        "vendor_name": vendor_name,
        "data": payload,
    }
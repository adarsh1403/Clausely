from typing import Any, Optional
from app.config import Settings, get_settings


# Evaluates whether the liability cap complies with corporate limits
def audit_liability_cap(
    annual_value: float,
    liability_cap: float,
    settings: Settings,
) -> dict[str, Any]:
    # Maximum allowed cap is the smaller of the annual multiple and the hard USD limit
    multiple_limit = settings.POLICY_LIABILITY_ANNUAL_MULTIPLE * annual_value
    max_allowed = min(multiple_limit, settings.POLICY_MAX_LIABILITY_CAP_USD)
    passed = liability_cap <= max_allowed

    if passed:
        message = f"Liability cap (${liability_cap:,.2f}) is within allowed threshold (${max_allowed:,.2f})."
    else:
        message = f"Liability cap (${liability_cap:,.2f}) exceeds maximum allowed threshold (${max_allowed:,.2f})."

    return {
        "rule": "LIABILITY_CAP",
        "severity": "HIGH",
        "passed": passed,
        "message": message,
    }


# Evaluates whether renewal notice days meet minimum policy requirements
def audit_renewal_notice(
    auto_renewal: bool,
    renewal_notice_days: int,
    settings: Settings,
) -> dict[str, Any]:
    min_days = settings.POLICY_MIN_RENEWAL_NOTICE_DAYS

    # Auto-renewal rule only applies when auto_renewal is enabled
    if not auto_renewal:
        return {
            "rule": "RENEWAL_NOTICE",
            "severity": "MEDIUM",
            "passed": True,
            "message": "Auto-renewal is disabled; renewal notice requirement does not apply.",
        }

    passed = renewal_notice_days >= min_days
    if passed:
        message = f"Renewal notice ({renewal_notice_days} days) meets minimum requirement ({min_days} days)."
    else:
        message = f"Renewal notice ({renewal_notice_days} days) is below minimum requirement ({min_days} days)."

    return {
        "rule": "RENEWAL_NOTICE",
        "severity": "MEDIUM",
        "passed": passed,
        "message": message,
    }


# Evaluates whether the contract governing law is in the approved jurisdictions list
def audit_governing_law(governing_law: str, settings: Settings) -> dict[str, Any]:
    approved = settings.get_approved_jurisdictions()
    normalized_law = governing_law.strip().upper()
    passed = normalized_law in approved

    if passed:
        message = f"Governing law ({normalized_law}) is in the approved list ({', '.join(approved)})."
    else:
        message = f"Governing law ({normalized_law}) is not in the approved list ({', '.join(approved)})."

    return {
        "rule": "GOVERNING_LAW",
        "severity": "HIGH",
        "passed": passed,
        "message": message,
    }


# Evaluates whether termination notice days meet minimum policy requirements
def audit_termination_notice(
    termination_notice_days: int,
    settings: Settings,
) -> dict[str, Any]:
    min_days = settings.POLICY_MIN_TERMINATION_NOTICE_DAYS
    passed = termination_notice_days >= min_days

    if passed:
        message = f"Termination notice ({termination_notice_days} days) meets minimum requirement ({min_days} days)."
    else:
        message = f"Termination notice ({termination_notice_days} days) is below minimum requirement ({min_days} days)."

    return {
        "rule": "TERMINATION_NOTICE",
        "severity": "LOW",
        "passed": passed,
        "message": message,
    }


# Runs all compliance checks and determines whether human review is required
def audit_contract_compliance(
    extracted_data: dict[str, Any],
    settings: Optional[Settings] = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()

    findings = [
        audit_liability_cap(
            float(extracted_data.get("annual_value", 0.0)),
            float(extracted_data.get("liability_cap_amount", 0.0)),
            active_settings,
        ),
        audit_renewal_notice(
            bool(extracted_data.get("auto_renewal", False)),
            int(extracted_data.get("renewal_notice_days", 0)),
            active_settings,
        ),
        audit_governing_law(
            str(extracted_data.get("governing_law", "")),
            active_settings,
        ),
        audit_termination_notice(
            int(extracted_data.get("termination_notice_days", 0)),
            active_settings,
        ),
    ]

    # Route to human review only if at least one HIGH severity check failed
    has_high_violation = any(
        finding["severity"] == "HIGH" and not finding["passed"]
        for finding in findings
    )

    if has_high_violation:
        requires_human_review = True
        status = "REVIEW_REQUIRED"
    else:
        requires_human_review = False
        status = "APPROVED"

    return {
        "compliance_findings": findings,
        "requires_human_review": requires_human_review,
        "status": status,
    }

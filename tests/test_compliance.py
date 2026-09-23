from app.compliance import audit_contract_compliance
from app.config import Settings


# Helper returning default test settings without reading local .env
def get_test_settings() -> Settings:
    return Settings(
        POLICY_MAX_LIABILITY_CAP_USD=500000.0,
        POLICY_LIABILITY_ANNUAL_MULTIPLE=2.0,
        POLICY_MIN_RENEWAL_NOTICE_DAYS=30,
        POLICY_MIN_TERMINATION_NOTICE_DAYS=30,
        POLICY_APPROVED_JURISDICTIONS="US-DE,US-NY,US-CA,UK",
        _env_file=None,
    )


# Tests that a compliant contract passes all checks and is automatically approved
def test_audit_fully_compliant_contract():
    data = {
        "annual_value": 100000.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 45,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "APPROVED"
    assert result["requires_human_review"] is False
    assert all(finding["passed"] for finding in result["compliance_findings"])


# Tests that a liability cap exceeding the hard USD limit triggers a HIGH violation
def test_audit_liability_cap_exceeds_max_usd():
    data = {
        "annual_value": 400000.0,
        "liability_cap_amount": 600000.0,
        "governing_law": "US-NY",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["requires_human_review"] is True
    cap_finding = next(f for f in result["compliance_findings"] if f["rule"] == "LIABILITY_CAP")
    assert cap_finding["passed"] is False
    assert cap_finding["severity"] == "HIGH"


# Tests that a liability cap exceeding the annual multiple triggers a HIGH violation
def test_audit_liability_cap_exceeds_annual_multiple():
    data = {
        "annual_value": 100000.0,
        "liability_cap_amount": 250000.0,
        "governing_law": "US-CA",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["requires_human_review"] is True
    cap_finding = next(f for f in result["compliance_findings"] if f["rule"] == "LIABILITY_CAP")
    assert cap_finding["passed"] is False


# Tests that an unapproved governing law triggers a HIGH violation and requires review
def test_audit_unapproved_jurisdiction():
    data = {
        "annual_value": 50000.0,
        "liability_cap_amount": 50000.0,
        "governing_law": "KY-CAYMAN",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["requires_human_review"] is True
    law_finding = next(f for f in result["compliance_findings"] if f["rule"] == "GOVERNING_LAW")
    assert law_finding["passed"] is False
    assert law_finding["severity"] == "HIGH"


# Tests that a MEDIUM severity renewal violation is recorded without blocking approval
def test_audit_renewal_notice_medium_severity_does_not_block():
    data = {
        "annual_value": 100000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "UK",
        "auto_renewal": True,
        "renewal_notice_days": 15,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "APPROVED"
    assert result["requires_human_review"] is False
    renewal_finding = next(f for f in result["compliance_findings"] if f["rule"] == "RENEWAL_NOTICE")
    assert renewal_finding["passed"] is False
    assert renewal_finding["severity"] == "MEDIUM"


# Tests that a LOW severity termination violation is recorded without blocking approval
def test_audit_termination_notice_low_severity_does_not_block():
    data = {
        "annual_value": 100000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 10,
    }
    result = audit_contract_compliance(data, get_test_settings())

    assert result["status"] == "APPROVED"
    assert result["requires_human_review"] is False
    term_finding = next(f for f in result["compliance_findings"] if f["rule"] == "TERMINATION_NOTICE")
    assert term_finding["passed"] is False
    assert term_finding["severity"] == "LOW"


# Tests that renewal notice requirement passes when auto_renewal is False
def test_audit_auto_renewal_false_passes_renewal_check():
    data = {
        "annual_value": 50000.0,
        "liability_cap_amount": 50000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
        "renewal_notice_days": 0,
        "termination_notice_days": 30,
    }
    result = audit_contract_compliance(data, get_test_settings())

    renewal_finding = next(f for f in result["compliance_findings"] if f["rule"] == "RENEWAL_NOTICE")
    assert renewal_finding["passed"] is True

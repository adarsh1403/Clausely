import datetime
import pytest
from pydantic import ValidationError
from app.schemas import VendorContract


# Tests valid vendor contract creation and automatic date string parsing
def test_valid_vendor_contract():
    data = {
        "vendor_name": "CloudCorp Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 120000.0,
        "liability_cap_amount": 240000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 60,
    }
    contract = VendorContract(**data)
    assert contract.vendor_name == "CloudCorp Inc"
    assert contract.effective_date == datetime.date(2025, 1, 1)
    assert contract.expiration_date == datetime.date(2026, 1, 1)
    assert contract.annual_value == 120000.0
    assert contract.liability_cap_amount == 240000.0
    assert contract.governing_law == "US-DE"
    assert contract.auto_renewal is True


# Tests default values for optional notice day fields
def test_default_notice_days():
    data = {
        "vendor_name": "CloudCorp Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 50000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "US-NY",
        "auto_renewal": False,
    }
    contract = VendorContract(**data)
    assert contract.renewal_notice_days == 0
    assert contract.termination_notice_days == 0


# Tests that negative monetary amounts raise validation errors
def test_negative_monetary_values_fail():
    base_data = {
        "vendor_name": "CloudCorp Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 1000.0,
        "liability_cap_amount": 2000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
    }

    # Test negative annual value
    with pytest.raises(ValidationError):
        VendorContract(**{**base_data, "annual_value": -10.0})

    # Test negative liability cap
    with pytest.raises(ValidationError):
        VendorContract(**{**base_data, "liability_cap_amount": -50.0})


# Tests that negative notice day integers raise validation errors
def test_negative_notice_days_fail():
    base_data = {
        "vendor_name": "CloudCorp Inc",
        "customer_name": "Acme Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 1000.0,
        "liability_cap_amount": 2000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
    }

    # Test negative renewal notice days
    with pytest.raises(ValidationError):
        VendorContract(**{**base_data, "renewal_notice_days": -1})

    # Test negative termination notice days
    with pytest.raises(ValidationError):
        VendorContract(**{**base_data, "termination_notice_days": -5})


# Tests that invalid date strings raise validation errors
def test_invalid_date_formats():
    base_data = {
        "vendor_name": "CloudCorp Inc",
        "customer_name": "Acme Corp",
        "effective_date": "not-a-valid-date",
        "expiration_date": "2026-01-01",
        "annual_value": 1000.0,
        "liability_cap_amount": 2000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
    }
    with pytest.raises(ValidationError):
        VendorContract(**base_data)


# Tests that missing required fields raise validation errors
def test_missing_required_fields():
    with pytest.raises(ValidationError):
        VendorContract(vendor_name="Incomplete Data")

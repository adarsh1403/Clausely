import json
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from app.config import Settings
from app.validation import execute_extraction_with_retry, validate_raw_extraction


# Tests validating a well-formed JSON string matching the schema
def test_validate_raw_extraction_valid():
    valid_payload = {
        "vendor_name": "CloudServices Inc",
        "customer_name": "Global Retail Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 100000.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
        "renewal_notice_days": 30,
        "termination_notice_days": 30,
    }
    raw_json = json.dumps(valid_payload)
    data, errors = validate_raw_extraction(raw_json)

    assert data is not None
    assert errors == []
    assert data["vendor_name"] == "CloudServices Inc"
    assert data["effective_date"] == "2025-01-01"


# Tests that malformed non-JSON text yields a syntax error
def test_validate_raw_extraction_syntax_error():
    raw_json = "This is not json { broken:"
    data, errors = validate_raw_extraction(raw_json)

    assert data is None
    assert len(errors) == 1
    assert "Invalid JSON syntax" in errors[0]


# Tests that valid JSON arrays or scalar types are rejected
def test_validate_raw_extraction_non_dictionary():
    raw_json = json.dumps(["not", "a", "dictionary"])
    data, errors = validate_raw_extraction(raw_json)

    assert data is None
    assert len(errors) == 1
    assert "Expected a JSON object" in errors[0]


# Tests that schema constraint violations return descriptive field error messages
def test_validate_raw_extraction_pydantic_error():
    invalid_payload = {
        "vendor_name": "CloudServices Inc",
        "customer_name": "Global Retail Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": -100.0,
        "liability_cap_amount": 200000.0,
        "governing_law": "US-DE",
        "auto_renewal": True,
    }
    raw_json = json.dumps(invalid_payload)
    data, errors = validate_raw_extraction(raw_json)

    assert data is None
    assert any("annual_value" in err for err in errors)


# Tests that the reflection loop succeeds when LLM corrects itself on retry
def test_self_healing_success_on_retry():
    # Setup mock LLM: first response has negative annual_value, second is valid
    invalid_json = json.dumps({
        "vendor_name": "CloudServices Inc",
        "customer_name": "Global Retail Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": -50.0,
        "liability_cap_amount": 100.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
    })
    valid_json = json.dumps({
        "vendor_name": "CloudServices Inc",
        "customer_name": "Global Retail Corp",
        "effective_date": "2025-01-01",
        "expiration_date": "2026-01-01",
        "annual_value": 50000.0,
        "liability_cap_amount": 100000.0,
        "governing_law": "US-DE",
        "auto_renewal": False,
    })

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [
        AIMessage(content=invalid_json),
        AIMessage(content=valid_json),
    ]

    result = execute_extraction_with_retry("Contract text", llm=mock_llm)

    assert result["status"] == "PROCESSING"
    assert result["retry_count"] == 1
    assert result["requires_human_review"] is False
    assert result["extracted_data"]["annual_value"] == 50000.0
    assert mock_llm.invoke.call_count == 2


# Tests that exceeding maximum retries flags the document as failed
def test_self_healing_exhausts_retries():
    # Setup mock LLM returning invalid JSON consistently
    invalid_json = json.dumps({"vendor_name": "Incomplete Contract"})
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content=invalid_json)

    custom_settings = Settings(
        MAX_EXTRACTION_RETRIES=2,
        _env_file=None,
    )

    result = execute_extraction_with_retry(
        "Contract text",
        settings=custom_settings,
        llm=mock_llm,
    )

    assert result["status"] == "FAILED"
    assert result["requires_human_review"] is True
    assert result["retry_count"] == 2
    assert result["extracted_data"] is None
    assert len(result["validation_errors"]) > 0
    # 1 initial call + 2 retries = 3 calls total
    assert mock_llm.invoke.call_count == 3

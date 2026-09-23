from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from app.config import Settings
from app.llm import (
    build_extraction_prompt,
    clean_json_response,
    extract_contract,
    get_llm,
)


# Tests that initial prompt contains all required fields and does not include feedback
def test_build_extraction_prompt_initial():
    prompt = build_extraction_prompt("Vendor agreement between Acme and Beta.")
    assert "vendor_name" in prompt
    assert "customer_name" in prompt
    assert "annual_value" in prompt
    assert "liability_cap_amount" in prompt
    assert "governing_law" in prompt
    assert "Vendor agreement between Acme and Beta." in prompt
    assert "CRITICAL" not in prompt


# Tests that previous validation errors are injected into retry prompt
def test_build_extraction_prompt_with_errors():
    errors = [
        "annual_value must be greater than or equal to 0",
        "effective_date must be in YYYY-MM-DD format",
    ]
    prompt = build_extraction_prompt("Contract text", validation_errors=errors)
    assert "CRITICAL: The previous extraction failed validation" in prompt
    assert "- annual_value must be greater than or equal to 0" in prompt
    assert "- effective_date must be in YYYY-MM-DD format" in prompt


# Tests that markdown json code fences are stripped properly
def test_clean_json_response_with_markdown_fences():
    raw_response = "```json\n{\"vendor_name\": \"Acme Corp\"}\n```"
    cleaned = clean_json_response(raw_response)
    assert cleaned == "{\"vendor_name\": \"Acme Corp\"}"


# Tests that raw unformatted JSON strings are preserved intact
def test_clean_json_response_already_clean():
    raw_response = "{\"vendor_name\": \"Acme Corp\"}"
    cleaned = clean_json_response(raw_response)
    assert cleaned == "{\"vendor_name\": \"Acme Corp\"}"


# Tests contract extraction end-to-end with a mocked LLM invocation
def test_extract_contract_mocked():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content="```json\n{\"vendor_name\": \"Mocked Vendor\", \"annual_value\": 50000.0}\n```"
    )

    result = extract_contract("Sample contract text", llm=mock_llm)
    assert result == "{\"vendor_name\": \"Mocked Vendor\", \"annual_value\": 50000.0}"
    mock_llm.invoke.assert_called_once()


# Tests that get_llm applies parameters from the supplied settings
def test_get_llm_configuration():
    custom_settings = Settings(
        GEMINI_MODEL="gemini-1.5-pro",
        GEMINI_API_KEY="test-api-key",
        _env_file=None,
    )
    llm = get_llm(custom_settings)
    assert llm.model == "gemini-1.5-pro"

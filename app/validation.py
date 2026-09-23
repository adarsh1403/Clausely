import json
from typing import Any, Optional
from pydantic import ValidationError
from app.config import Settings, get_settings
from app.llm import extract_contract
from app.schemas import VendorContract


# Formats Pydantic validation errors into readable strings for LLM feedback
def format_pydantic_errors(error: ValidationError) -> list[str]:
    formatted = []
    for err in error.errors():
        # Build field path omitting root symbol
        location = " -> ".join(str(loc) for loc in err["loc"] if loc != "__root__")
        message = err["msg"]
        formatted.append(f"{location}: {message}")
    return formatted


# Validates raw JSON string against the VendorContract schema
def validate_raw_extraction(raw_json: str) -> tuple[Optional[dict[str, Any]], list[str]]:
    # Attempt to parse raw string into JSON
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, [f"Invalid JSON syntax: {str(exc)}"]

    # Ensure top-level payload is a dictionary
    if not isinstance(data, dict):
        return None, ["Expected a JSON object (dictionary) at root."]

    # Validate dictionary against Pydantic schema
    try:
        contract = VendorContract.model_validate(data)
        # Use mode='json' to serialize date fields to ISO string format
        return contract.model_dump(mode="json"), []
    except ValidationError as exc:
        return None, format_pydantic_errors(exc)


# Runs the extraction and self-correction retry loop until valid or retries exhausted
def execute_extraction_with_retry(
    raw_text: str,
    settings: Optional[Settings] = None,
    llm: Any = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    max_retries = active_settings.MAX_EXTRACTION_RETRIES

    retry_count = 0
    validation_errors: Optional[list[str]] = None

    while retry_count <= max_retries:
        # Extract fields from contract text, injecting errors on retries
        raw_json = extract_contract(raw_text, validation_errors, llm=llm)
        extracted_data, errors = validate_raw_extraction(raw_json)

        # Return successfully if validation passes
        if extracted_data is not None:
            return {
                "extracted_data": extracted_data,
                "validation_errors": [],
                "retry_count": retry_count,
                "status": "PROCESSING",
                "requires_human_review": False,
            }

        # Save errors and increment retry attempt counter
        validation_errors = errors
        retry_count += 1

    # Flag for human review when all retry attempts fail
    return {
        "extracted_data": None,
        "validation_errors": validation_errors or ["Max extraction retries exceeded."],
        "retry_count": max_retries,
        "status": "FAILED",
        "requires_human_review": True,
    }

from typing import Optional
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import Settings, get_settings


# Returns an initialized ChatGoogleGenerativeAI client based on settings
def get_llm(settings: Optional[Settings] = None) -> ChatGoogleGenerativeAI:
    active_settings = settings or get_settings()
    return ChatGoogleGenerativeAI(
        model=active_settings.GEMINI_MODEL,
        google_api_key=active_settings.GEMINI_API_KEY,
        temperature=0.0,
    )


# Builds prompt instructing the LLM to extract structured contract data
def build_extraction_prompt(
    raw_text: str,
    validation_errors: Optional[list[str]] = None,
) -> str:
    schema_description = """You are a contract extraction assistant. Extract the following fields from the contract text into a valid JSON object:
- vendor_name: Legal name of the vendor (string)
- customer_name: Legal name of the customer (string)
- effective_date: Contract start date in YYYY-MM-DD format (string)
- expiration_date: Contract end date in YYYY-MM-DD format (string)
- annual_value: Annual contract value in USD as a number (float, >= 0.0)
- liability_cap_amount: Total liability cap in USD as a number (float, >= 0.0)
- governing_law: Jurisdiction code, e.g. US-DE, US-NY, US-CA, UK (string)
- auto_renewal: Whether the contract automatically renews (boolean)
- renewal_notice_days: Notice days required to prevent renewal (integer, >= 0, default 0)
- termination_notice_days: Notice days for termination for convenience (integer, >= 0, default 0)

Return ONLY the raw JSON object. Do not wrap in markdown fences or include conversational text."""

    # Inject validation error feedback if this is a correction retry
    if validation_errors:
        error_lines = "\n".join(f"- {error}" for error in validation_errors)
        feedback_section = f"\n\nCRITICAL: The previous extraction failed validation with these errors:\n{error_lines}\nYou must fix these specific errors in your output."
    else:
        feedback_section = ""

    return f"{schema_description}{feedback_section}\n\nCONTRACT TEXT:\n{raw_text}"


# Strips markdown code blocks and whitespace from raw LLM output
def clean_json_response(raw_response: str) -> str:
    cleaned = raw_response.strip()

    # Remove markdown code fences if the model included them
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


# Calls the LLM to extract contract fields and returns cleaned JSON string
def extract_contract(
    raw_text: str,
    validation_errors: Optional[list[str]] = None,
    llm: Optional[ChatGoogleGenerativeAI] = None,
) -> str:
    active_llm = llm or get_llm()
    prompt = build_extraction_prompt(raw_text, validation_errors)
    response = active_llm.invoke(prompt)

    # Extract text content whether returned as a string or list of content blocks
    raw_content = response.content if isinstance(response, AIMessage) else response
    if isinstance(raw_content, list):
        # Extract text field from block dictionaries or strings in list
        parts = []
        for part in raw_content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            else:
                parts.append(str(part))
        content = "".join(parts)
    else:
        content = str(raw_content)

    return clean_json_response(content)

from datetime import date
from pydantic import BaseModel, Field


# Schema for structured vendor contract extraction
class VendorContract(BaseModel):
    vendor_name: str = Field(..., description="Legal name of the vendor providing services")
    customer_name: str = Field(..., description="Legal name of the customer organization")
    effective_date: date = Field(..., description="Start date of the contract agreement")
    expiration_date: date = Field(..., description="End date of the contract agreement")
    annual_value: float = Field(..., ge=0.0, description="Annual contract value in USD")
    liability_cap_amount: float = Field(..., ge=0.0, description="Total liability cap in USD")
    governing_law: str = Field(..., description="Jurisdiction code (e.g., US-DE, US-NY, US-CA, UK)")
    auto_renewal: bool = Field(..., description="Whether the contract automatically renews")
    renewal_notice_days: int = Field(default=0, ge=0, description="Days notice required to prevent renewal")
    termination_notice_days: int = Field(default=0, ge=0, description="Notice days for termination for convenience")

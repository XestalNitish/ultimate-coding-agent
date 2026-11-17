# Pydantic V2 Core Reference

## BaseModel and Field Specifications
Define validated schemas with default values, constraints, and descriptions.

```python
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

class UserProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    age: int = Field(..., ge=18, le=120, description="Age in years")
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

## Field Validators and Model Validators
Custom validation logic using `field_validator` and `model_validator`.

```python
from pydantic import field_validator, model_validator

class Transaction(BaseModel):
    account_id: str
    amount: float = Field(gt=0)
    currency: str = "INR"

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        allowed = {"INR", "USD", "EUR", "GBP"}
        if v.upper() not in allowed:
            raise ValueError(f"Currency {v} is not supported. Choose from {allowed}")
        return v.upper()

    @model_validator(mode="after")
    def verify_account(self) -> "Transaction":
        if self.account_id.startswith("TEST") and self.amount > 10000:
            raise ValueError("Test accounts cannot exceed 10,000 limit")
        return self
```

## Serialization & Dict Export
Export to Python dictionaries or JSON strings cleanly.

```python
tx = Transaction(account_id="ACC123", amount=500.0)

# Export to dict (replaces .dict() from v1)
data = tx.model_dump(exclude_none=True)

# Export to JSON (replaces .json() from v1)
json_str = tx.model_dump_json(indent=2)
```

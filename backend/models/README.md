# Backend Models Directory

This directory contains Pydantic models and data schemas for the RealAICoach backend.

## Structure

```
models/
├── __init__.py           # Package initialization
├── auth.py              # Authentication models (User, Login, Register, etc.)
├── jobs.py              # Job platform models (Job, Application, etc.)
├── payments.py          # Payment models (Invoice, Subscription, etc.)
├── common.py            # Shared base models and utilities
└── README.md            # This file
```

## Guidelines

### 1. Model Organization
- Group related models by domain (auth, jobs, payments, etc.)
- Keep models focused and single-responsibility
- Use composition over inheritance where possible

### 2. Naming Conventions
- Request models: `{Action}Request` (e.g., `LoginRequest`, `CreateJobRequest`)
- Response models: `{Entity}Response` (e.g., `UserResponse`, `JobListResponse`)
- Database models: `{Entity}DB` (e.g., `UserDB`, `JobDB`)
- Update models: `{Entity}Update` (e.g., `UserUpdate`, `JobUpdate`)

### 3. Model Features
```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class ExampleModel(BaseModel):
    """Clear docstring explaining the model purpose."""
    
    id: str = Field(..., description="Unique identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    optional_field: Optional[str] = None
    
    @field_validator('id')
    @classmethod
    def validate_id(cls, v):
        if not v:
            raise ValueError("ID cannot be empty")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "user_123",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }
```

### 4. Migration Plan
Models will be gradually extracted from route files into this directory.

**Priority:**
1. Common/shared models (auth, base classes)
2. Frequently used models (user, job, payment)
3. Domain-specific models

## Future Enhancements
- Add model validators for complex business logic
- Create base classes for common patterns (timestamps, soft delete, etc.)
- Add JSON schema generation for API documentation

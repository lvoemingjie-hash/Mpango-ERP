"""
Common Pydantic schemas for Mpango ERP.
Implements openapi.yaml common component schemas.
"""
from typing import Generic, TypeVar, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


T = TypeVar("T")


class Pagination(BaseModel):
    """
    Pagination metadata.
    Implements openapi.yaml Pagination schema.
    """
    page: int = Field(..., ge=1, description="Current page number (1-based)")
    size: int = Field(..., ge=1, le=100, description="Items per page")
    total: int = Field(..., ge=0, description="Total number of items")
    pages: int = Field(..., ge=0, description="Total number of pages")
    
    model_config = {"from_attributes": True}


class ErrorDetail(BaseModel):
    """
    Error detail for validation errors.
    Implements openapi.yaml ErrorDetail schema.
    """
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    meta: Optional[dict[str, Any]] = Field(None, description="Additional error metadata")
    
    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """
    Standard error response.
    Implements openapi.yaml ErrorResponse schema.
    """
    success: bool = Field(False, description="Always false for errors")
    error: dict[str, Any] = Field(
        ...,
        description="Error object with code, message, and optional details"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp"
    )
    
    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """
    Simple message response.
    Implements openapi.yaml MessageResponse schema.
    """
    success: bool = Field(True, description="Operation success status")
    message: str = Field(..., description="Response message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}


class DataResponse(BaseModel, Generic[T]):
    """
    Generic data response wrapper.
    Wraps response data with success flag and timestamp.
    
    Used for all successful API responses per openapi.yaml pattern.
    """
    success: bool = Field(True, description="Always true for successful responses")
    data: T = Field(..., description="Response data")
    message: Optional[str] = Field(None, description="Optional message")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated data response.
    Combines data items with pagination metadata.
    """
    success: bool = Field(True, description="Always true for successful responses")
    data: dict[str, Any] = Field(
        ...,
        description="Data object containing items and pagination"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Response timestamp"
    )
    
    model_config = {"from_attributes": True}

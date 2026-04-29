"""
Core domain entity: Resource

Everything in the platform is treated as a resource with key-value metadata labels.
This is the base abstraction that all domain entities (experiments, runs, datasets, etc.) reference.
"""

import uuid
from pydantic import BaseModel, Field
from typing import Optional


class Resource(BaseModel):
    """A platform resource with arbitrary key-value labels for metadata."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    labels: dict = Field(default_factory=dict)


class ResourceCreate(BaseModel):
    """Schema for creating a new resource."""
    labels: dict = Field(default_factory=dict)

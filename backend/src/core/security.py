"""
Security utilities for validating data before database operations.

This module provides validation functions to prevent SQL injection
and other security vulnerabilities.
"""
from typing import List


def validate_embedding_values(embedding: List[float]) -> None:
    """
    Validate embedding values to prevent SQL injection attacks.
    
    Args:
        embedding: List of float values representing an embedding vector
        
    Raises:
        ValueError: If embedding contains invalid values
        
    Security:
        - Ensures all values are numeric (prevents string injection)
        - Validates values are in reasonable range (prevents overflow)
        - Rejects empty embeddings
    """
    if not embedding:
        raise ValueError("Embedding cannot be empty")
    
    if not isinstance(embedding, list):
        raise ValueError(f"Embedding must be a list, got {type(embedding).__name__}")
    
    if not all(isinstance(x, (int, float)) for x in embedding):
        invalid_types = set(type(x).__name__ for x in embedding if not isinstance(x, (int, float)))
        raise ValueError(
            f"Embedding must contain only numeric values. "
            f"Found invalid types: {', '.join(invalid_types)}"
        )
    
    # Check for special float values that could cause issues
    if any(x != x for x in embedding):  # NaN check
        raise ValueError("Embedding cannot contain NaN values")
    
    if any(abs(x) == float('inf') for x in embedding):
        raise ValueError("Embedding cannot contain infinite values")
    
    # Reasonable range check (typical embeddings are normalized between -1 and 1,
    # but we allow wider range for different embedding models)
    if any(abs(x) > 1e10 for x in embedding):
        raise ValueError("Embedding values out of reasonable range (abs value > 1e10)")


__all__ = ['validate_embedding_values']

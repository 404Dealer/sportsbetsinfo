"""Custom exceptions for the sportsbetsinfo platform."""


class SportsBetsInfoError(Exception):
    """Base exception for all sportsbetsinfo errors."""

    pass


class IntegrityError(SportsBetsInfoError):
    """Raised when data integrity check fails."""

    pass


class HashMismatchError(IntegrityError):
    """Raised when computed hash doesn't match stored hash."""

    def __init__(self, entity_type: str, entity_id: str, expected: str, actual: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash mismatch for {entity_type} {entity_id}: "
            f"expected {expected[:16]}..., got {actual[:16]}..."
        )


class ImmutabilityViolationError(SportsBetsInfoError):
    """Raised when attempting to modify immutable data."""

    def __init__(self, operation: str, table: str) -> None:
        self.operation = operation
        self.table = table
        super().__init__(f"Cannot {operation} on immutable table '{table}'")


class EntityNotFoundError(SportsBetsInfoError):
    """Raised when a requested entity doesn't exist."""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")


class DuplicateEntityError(SportsBetsInfoError):
    """Raised when attempting to insert a duplicate entity."""

    def __init__(self, entity_type: str, hash_value: str) -> None:
        self.entity_type = entity_type
        self.hash_value = hash_value
        super().__init__(
            f"Duplicate {entity_type} with hash {hash_value[:16]}... already exists"
        )


class APIError(SportsBetsInfoError):
    """Raised when an external API call fails."""

    def __init__(self, client: str, message: str, status_code: int | None = None) -> None:
        self.client = client
        self.status_code = status_code
        super().__init__(f"{client} API error: {message}" +
                        (f" (status {status_code})" if status_code else ""))


class ConfigurationError(SportsBetsInfoError):
    """Raised when configuration is invalid or missing."""

    pass

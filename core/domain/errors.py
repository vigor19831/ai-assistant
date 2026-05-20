"""Domain exceptions."""


class ConfigurationError(Exception):
    """Invalid configuration."""

    pass


class AdapterError(Exception):
    """Adapter operation failed."""

    pass


class VersionMismatchError(Exception):
    """Index/model version mismatch."""

    pass

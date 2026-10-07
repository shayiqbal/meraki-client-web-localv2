"""Application-facing API exceptions."""


class MerakiClientError(RuntimeError):
    """A user-safe Meraki API error."""


class AuthenticationError(MerakiClientError):
    """API credentials are absent or rejected."""


class CompatibilityError(MerakiClientError):
    """The tenant, firmware, endpoint, or SDK lacks a requested capability."""

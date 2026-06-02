"""Compile-time safety test for router assembly.

Ensures that all explicitly imported feature handler modules
are importable and that assemble_routers() succeeds without
deferred runtime import errors.
"""

import pytest
from fastapi import APIRouter

# Import must succeed at test collection time (compile time).
# A missing or broken feature handlers.py will fail here immediately.
from ai_assistant.api.router import assemble_routers


def test_assemble_routers_returns_routers() -> None:
    """assemble_routers should return a list of APIRouter instances."""
    routers = assemble_routers()
    assert isinstance(routers, list)
    for router in routers:
        assert isinstance(router, APIRouter)

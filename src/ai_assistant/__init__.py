"""Adapters package — no side-effect imports, no @register.

Adapters are loaded on-demand via create_adapter() in adapters/factory.py.
"""

__all__ = []  # Explicitly empty — adapters are not imported at package level

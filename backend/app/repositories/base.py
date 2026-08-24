"""
Repository-layer foundation.

Establishes the pattern (Router -> Service -> Repository -> Database)
required by CLAUDE.md §7 / IMPLEMENTATION_BLUEPRINT.md. No concrete
repository is implemented yet — that requires the schema from
docs/DATABASE_SCHEMA.md, which is Phase 2 scope.

Concrete repositories (Phase 2+) subclass Repository and encapsulate all
direct data access for one aggregate (e.g. TripsRepository), so services
never issue raw queries themselves.
"""

from __future__ import annotations


class Repository:
    """Marker base class for data-access repositories.

    Intentionally empty in Phase 1 — no business tables exist yet, so
    there is no shared behavior to make abstract. Kept as a real module
    (not a placeholder comment) so Phase 2 has a stable import path
    (`app.repositories.base.Repository`) to subclass from, rather than
    introducing the pattern for the first time alongside the first real
    repository. Phase 2 should add the actual shared contract (e.g.
    `get_connection()`) here as concrete repositories reveal what it
    needs to be.
    """

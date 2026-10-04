"""Pure, dependency-free business logic.

Everything here is deterministic and side-effect-free so it can be unit-tested
without a database, network, or FastAPI app. Routers and services call into these
functions; the rules live in exactly one place.
"""

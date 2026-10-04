"""Service layer — reusable business operations shared by routers.

Routers stay thin: they validate input and call these services, which own the
cross-collection logic (sessions, gamification, push fan-out). This keeps the
same operation identical no matter which endpoint triggers it.
"""

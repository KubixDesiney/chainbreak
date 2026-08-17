"""Runtime data shipped with the wheel.

The source checkout keeps schemas and scenarios at repository level because
they are also authoring artifacts.  The wheel maps them here so runtime code
can access them through :mod:`importlib.resources` without a checkout.
"""

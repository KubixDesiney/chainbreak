"""Rendering evidence into terminal, Markdown and self-contained HTML reports (M16).

No business logic lives here beyond presentation: every fact a report states
is read from a sealed bundle via ``analysis/`` and ``scoring/``, never
computed fresh. ``reporting/language.py`` is the one place a rendering
decision gets enforced rather than merely documented -- see its module
docstring.
"""

from __future__ import annotations

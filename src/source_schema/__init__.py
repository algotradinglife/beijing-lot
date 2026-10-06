"""Data-source utilities and shared vocabulary.

The former "unified data source schema contract" (BJ-234 ``ddl``/``builder``/
``identity``/``feasibility``/``plan``/``handoff``/``manifest``) was a candidate
schema that production never adopted; its authoritative replacement is
``beidan_backend.catalog``. What remains:

* ``contract``     shared constants (time semantics, source families) still used
                   by the census; the table definitions it once paired with are
                   gone.
* ``census``, ``sources``  legacy-database census and hash verification used by
                   the BJ-252 temporal chain.
* ``publication``  crash-durable atomic writers (32 call sites).
"""

from . import contract  # noqa: F401
from . import census  # noqa: F401
from . import publication  # noqa: F401
from . import sources  # noqa: F401

__all__ = ["contract", "census", "publication", "sources"]

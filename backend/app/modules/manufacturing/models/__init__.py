"""Manufacturing models package (STRUCTURE §3: a models/ PACKAGE from the start, the inventory
precedent — one file per aggregate, each <400 lines).

PLAN 8.1's masters split by aggregate: ``workcenters`` (the work-centre resource), ``boms`` (the BOM
header + components), ``routings`` (the routing header + operations). Re-exported here so call sites
use one import (``from app.modules.manufacturing.models import Bom``) and the alembic env.py /
tenancy mapper-enumeration suite see every model through this package.
"""

from app.modules.manufacturing.models.boms import Bom, BomComponent
from app.modules.manufacturing.models.routings import Routing, RoutingOperation
from app.modules.manufacturing.models.workcenters import WorkCenter

__all__ = [
    "Bom",
    "BomComponent",
    "Routing",
    "RoutingOperation",
    "WorkCenter",
]

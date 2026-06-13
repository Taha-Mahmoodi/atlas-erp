"""Manufacturing schemas package (STRUCTURE §3: a schemas/ PACKAGE from the start, the sales
precedent) — split by aggregate so each file stays small and the router imports one surface.

- ``workcenters``: the work-centre Create/Update/Read/Filter.
- ``boms``: the BOM header Create/Update/Read/Filter + the BomComponent Create/Read sub-resource.
- ``routings``: the routing header Create/Update/Read/Filter + the RoutingOperation Create/Read
  sub-resource.
- ``production``: the production-order Create/Read/Detail/Filter + the exploded component/operation
  reads + the issue/finish action request bodies (PLAN 8.2).
"""

from app.modules.manufacturing.schemas.boms import (
    BomComponentCreate,
    BomComponentRead,
    BomCreate,
    BomFilter,
    BomRead,
    BomUpdate,
)
from app.modules.manufacturing.schemas.production import (
    ComponentIssueLine,
    FinishOrderRequest,
    IssueComponentsRequest,
    ProductionOrderComponentRead,
    ProductionOrderCreate,
    ProductionOrderDetail,
    ProductionOrderFilter,
    ProductionOrderOperationRead,
    ProductionOrderRead,
)
from app.modules.manufacturing.schemas.routings import (
    RoutingCreate,
    RoutingFilter,
    RoutingOperationCreate,
    RoutingOperationRead,
    RoutingRead,
    RoutingUpdate,
)
from app.modules.manufacturing.schemas.workcenters import (
    WorkCenterCreate,
    WorkCenterFilter,
    WorkCenterRead,
    WorkCenterUpdate,
)

__all__ = [
    "BomComponentCreate",
    "BomComponentRead",
    "BomCreate",
    "BomFilter",
    "BomRead",
    "BomUpdate",
    "ComponentIssueLine",
    "FinishOrderRequest",
    "IssueComponentsRequest",
    "ProductionOrderComponentRead",
    "ProductionOrderCreate",
    "ProductionOrderDetail",
    "ProductionOrderFilter",
    "ProductionOrderOperationRead",
    "ProductionOrderRead",
    "RoutingCreate",
    "RoutingFilter",
    "RoutingOperationCreate",
    "RoutingOperationRead",
    "RoutingRead",
    "RoutingUpdate",
    "WorkCenterCreate",
    "WorkCenterFilter",
    "WorkCenterRead",
    "WorkCenterUpdate",
]

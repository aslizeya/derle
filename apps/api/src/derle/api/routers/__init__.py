from fastapi import APIRouter

from derle.api.routers import analytics, datasets, demo, matching, uploads, workspaces

router = APIRouter(prefix="/api/v1")
for module in (workspaces, uploads, datasets, matching, analytics, demo):
    router.include_router(module.router)

__all__ = ["router"]

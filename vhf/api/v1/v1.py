from fastapi import APIRouter, Depends
from vhf.api.auth import require_api_key
from vhf.api.v1 import admin
from vhf.api.v1 import public

router = APIRouter()
router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)
router.include_router(public.router, tags=["public"])

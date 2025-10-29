from fastapi import APIRouter
from vhf.api.v1 import admin
from vhf.api.v1 import public
router = APIRouter()
router.include_router(admin.router,
                      prefix="/admin",
                      tags=["admin"])
router.include_router(public.router,
                      tags=["public"])
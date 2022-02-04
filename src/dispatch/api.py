from fastapi import APIRouter, Depends
from fastapi.openapi.docs import get_redoc_html
from fastapi.openapi.utils import get_openapi
from starlette.responses import JSONResponse

from dispatch.tag.views import router as tag_router
from dispatch.auth.service import get_current_user
from dispatch.job.views import router as job_router
from dispatch.worker.views import router as worker_router
from dispatch.service.planner_views import planner_router as planner_router


from dispatch.search.views import router as search_router
from dispatch.service.views import router as service_router
from dispatch.team.views import router as team_router
from dispatch.plugin.views import router as plugin_router
from dispatch.auth.views import user_router, auth_router

from dispatch.item.views import router as item_router
from dispatch.depot.views import router as depot_router
from dispatch.item_inventory.views import router as item_inventory_router


from dispatch.location.views import router as location_router
from dispatch.service_plugin.views import router as service_plugin_router
from dispatch.org.views import router as orgs_router


from .config import DISPATCH_AUTHENTICATION_PROVIDER_SLUG

api_router = APIRouter(
    default_response_class=JSONResponse
)  # WARNING: Don't use this unless you want unauthenticated routes
authenticated_api_router = APIRouter()

# NOTE we only advertise auth routes when basic auth is enabled
if DISPATCH_AUTHENTICATION_PROVIDER_SLUG == "dispatch-auth-provider-basic":
    api_router.include_router(auth_router, prefix="/auth", tags=["auth"])

# NOTE: All api routes should be authenticated by default
authenticated_api_router.include_router(user_router, prefix="/user", tags=["user"])
authenticated_api_router.include_router(tag_router, prefix="/tags", tags=["Tags"])
authenticated_api_router.include_router(service_router, prefix="/services", tags=["services"])
authenticated_api_router.include_router(team_router, prefix="/teams", tags=["teams"])
authenticated_api_router.include_router(worker_router, prefix="/workers", tags=["workers"])
authenticated_api_router.include_router(search_router, prefix="/search", tags=["search"])
authenticated_api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
authenticated_api_router.include_router(plugin_router, prefix="/plugins", tags=["plugins"])
authenticated_api_router.include_router(location_router, prefix="/locations", tags=["locations"])
authenticated_api_router.include_router(
    item_inventory_router, prefix="/item_inventory", tags=["item_inventory"])
authenticated_api_router.include_router(item_router, prefix="/items", tags=["items"])
authenticated_api_router.include_router(depot_router, prefix="/depots", tags=["depots"])

authenticated_api_router.include_router(orgs_router, prefix="/orgs", tags=["orgs"])

authenticated_api_router.include_router(
    service_plugin_router, prefix="/service_plugins", tags=["service_plugins"]
)
authenticated_api_router.include_router(
    planner_router, prefix="/planner_service", tags=["planner_service"]
)


doc_router = APIRouter()


@doc_router.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return JSONResponse(get_openapi(title="Dispatch Docs", version=1, routes=api_router.routes))


@doc_router.get("/", include_in_schema=False)
async def get_documentation():
    return get_redoc_html(openapi_url="/api/v1/docs/openapi.json", title="Dispatch Docs")


api_router.include_router(doc_router, prefix="/docs")


@api_router.get("/healthcheck", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}


api_router.include_router(authenticated_api_router, dependencies=[Depends(get_current_user)])

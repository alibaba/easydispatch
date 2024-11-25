from fastapi import APIRouter, Depends
from fastapi.openapi.docs import get_redoc_html
from fastapi.openapi.utils import get_openapi
from starlette.responses import JSONResponse


from dispatch.auth.service import get_current_user
from dispatch.job.views import router as job_router
from dispatch.worker.views import router as worker_router
from dispatch.planner_env.planner_views import planner_router


from dispatch.planner_service.views import router as service_router
from dispatch.team.views import router as team_router
from dispatch.plugin.views import router as plugin_router
from dispatch.auth.views import user_router, auth_router
from dispatch.cloudmarket.instance.views import router as instance_router

from dispatch.item.views import router as item_router
from dispatch.depot.views import router as depot_router
from dispatch.item_inventory.views import router as item_inventory_router


from dispatch.location.views import router as location_router
from dispatch.location_group.views import router as location_group_router
from dispatch.planner_plugin.views import router as service_plugin_router
from dispatch.org.views import router as orgs_router
from dispatch.route.views import router as route_router
# 2022-12-10 17:34:42 duan: temporary blocked because of table store. Will use pg db. 
# from dispatch.cloudmarket.instance.npl_views import router as npl_instance_router
from dispatch.order.views import router as order_router
# from dispatch.problem.views import router as problem_router
from dispatch.job_biz.views import router as job_biz_router
from dispatch.msg_template.views import router as msg_template_router
from dispatch.worker_absence.views import router as worker_absence_router

from .config import DISPATCH_AUTHENTICATION_PROVIDER_SLUG, BASE_ENV, ENABLE_ADDRESS_NORMALIZATION_ROUTER,DISPATCH_UI_URL
from dispatch.app.views import router as app_router

if ENABLE_ADDRESS_NORMALIZATION_ROUTER:
    from dispatch.cloudmarket.instance.address_normalization_views import router as address_normalization_router


api_router = APIRouter(
    default_response_class=JSONResponse
)  # WARNING: Don't use this unless you want unauthenticated routes
authenticated_api_router = APIRouter()

##########################################################################
# doc_exposed_api_router
##########################################################################
doc_exposed_api_router = APIRouter()
doc_exposed_api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
doc_exposed_api_router.include_router(user_router, prefix="/user", tags=["user"])
doc_exposed_api_router.include_router(orgs_router, prefix="/orgs", tags=["orgs"])

doc_exposed_api_router.include_router(team_router, prefix="/teams", tags=["teams"])
doc_exposed_api_router.include_router(worker_router, prefix="/workers", tags=["workers"])
doc_exposed_api_router.include_router(order_router, prefix="/orders", tags=["orders"])
doc_exposed_api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
doc_exposed_api_router.include_router(location_router, prefix="/locations", tags=["locations"])
doc_exposed_api_router.include_router(location_group_router, prefix="/location_group", tags=["location_group"])
doc_exposed_api_router.include_router(planner_router, prefix="/planner_service", tags=["planner_service"])
# doc_exposed_api_router.include_router(service_router, prefix="/services", tags=["services"])
##########################################################################
authenticated_api_router.include_router(app_router, prefix="/app", tags=["app"])




# NOTE we only advertise auth routes when basic auth is enabled
if DISPATCH_AUTHENTICATION_PROVIDER_SLUG == "dispatch-auth-provider-basic":
    api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
    api_router.include_router(
        instance_router, prefix="/instance", tags=["instance"]
    )
    # api_router.include_router(
    #     npl_instance_router,prefix="/instance_nlp",tags=["instance_nlp"]
    # )
    if ENABLE_ADDRESS_NORMALIZATION_ROUTER:    
        api_router.include_router(
            address_normalization_router, prefix="/instance_nlp", tags=["instance_nlp"]
        )

# NOTE: All api routes should be authenticated by default
authenticated_api_router.include_router(user_router, prefix="/user", tags=["user"])
authenticated_api_router.include_router(service_router, prefix="/services", tags=["services"])
authenticated_api_router.include_router(team_router, prefix="/teams", tags=["teams"])
authenticated_api_router.include_router(worker_router, prefix="/workers", tags=["workers"])
authenticated_api_router.include_router(job_router, prefix="/jobs", tags=["jobs"])
authenticated_api_router.include_router(plugin_router, prefix="/plugins", tags=["plugins"])
authenticated_api_router.include_router(location_router, prefix="/locations", tags=["locations"])
authenticated_api_router.include_router(location_group_router, prefix="/location_group", tags=["location_group"])


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
authenticated_api_router.include_router(
    route_router, prefix="/routes", tags=["routes"]
)
authenticated_api_router.include_router(
    order_router, prefix="/orders", tags=["orders"]
)
authenticated_api_router.include_router(
    job_biz_router, prefix="/job_biz", tags=["job_biz"]
)
authenticated_api_router.include_router(
    msg_template_router, prefix="/msg_template", tags=["msg_template"]
)
authenticated_api_router.include_router(
    worker_absence_router, prefix="/worker_absence", tags=["worker_absence"]
)

# Disabled from netflix dispatch
# authenticated_api_router.include_router(
#     problem_router, prefix="/problem", tags=["problem"]
# )
# authenticated_api_router.include_router(tag_router, prefix="/tags", tags=["Tags"])
# authenticated_api_router.include_router(search_router, prefix="/search", tags=["search"])


doc_router = APIRouter()


@doc_router.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return JSONResponse(get_openapi(title="Dispatch API Doc", version=1, routes=doc_exposed_api_router.routes))


@doc_router.get("/", include_in_schema=False)
async def get_documentation():
    # return get_redoc_html(openapi_url=f"/{BASE_ENV}/api/v1/docs/openapi.json", title="EasyDispatch API Document")
    return get_redoc_html(openapi_url=f"{DISPATCH_UI_URL}/{BASE_ENV}/api/v1/docs/openapi.json",
                          title="EasyDispatch API Document",)

api_router.include_router(doc_router, prefix="/docs")


@api_router.get("/healthcheck", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}


api_router.include_router(authenticated_api_router, dependencies=[Depends(get_current_user)])

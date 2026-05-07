from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.agent_gateway import router as agent_gateway_router
from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.alerts import router as alerts_router
from app.api.assets import router as assets_router
from app.api.control_domain import router as control_domain_router
from app.api.docs import router as docs_router
from app.api.control_platform import router as control_platform_router
from app.api.floor_plans import router as floor_plan_router
from app.api.integrations import router as integrations_router
from app.api.inspection import router as inspection_router
from app.api.learning import router as learning_router
from app.api.license import router as license_router
from app.api.llm import router as llm_router
from app.api.mobile import router as mobile_router
from app.api.notifications import router as notifications_router
from app.api.setup import router as setup_router
from app.api.storage import router as storage_router
from app.api.system import router as system_router
from app.api.topology import router as topology_router
from app.api.users import router as users_router
from app.api.work_orders import router as work_order_router
from app.core.database import init_database
from app.core.settings import settings
from app.ai_gateway.core.config_store import ensure_bootstrap as ensure_ai_gateway_bootstrap
from app.ai_gateway.core.config_store import record_service_access_event, validate_service_key
from app.services.bootstrap import seed_known_sources
from app.services.auth import SESSION_COOKIE_NAME, get_user_by_token, parse_bearer_token
from app.services.license import get_license_status


app = FastAPI(
    title="Yongjia Weak Current Ops Platform V2",
    version="2.0.0-dev",
    description="Clean rebuild line for the unified weak current operations platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3011",
        "http://localhost:3011",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https?://[^/]+:(3011|3000)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def license_guard(request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)

    if not settings.license_enforced:
        return await call_next(request)

    if path == "/api/system/health" or path.startswith("/api/license") or path.startswith("/assets"):
        return await call_next(request)

    if path.startswith("/api/"):
        status = get_license_status()
        if not status["active"]:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "license_required",
                        "message": status["reason"],
                        "machine_code": status["machine_code"],
                        "grace_deadline": status.get("grace_deadline"),
                    }
                },
            )

    return await call_next(request)


@app.middleware("http")
async def auth_guard(request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)

    if not path.startswith("/api/"):
        return await call_next(request)

    if path in {"/api/system/health", "/api/auth/login", "/api/auth/register"}:
        return await call_next(request)

    if path.startswith("/api/license") or path.startswith("/api/docs"):
        return await call_next(request)

    if path.startswith("/api/ai"):
        ai_key = request.headers.get("x-ai-gateway-key") or request.headers.get("X-AI-Gateway-Key")
        bearer_token = parse_bearer_token(request.headers.get("Authorization"))
        if not ai_key and bearer_token and bearer_token.startswith("yj-ai-"):
            ai_key = bearer_token
        if ai_key:
            client_host = request.client.host if request.client else ""
            ai_access = validate_service_key(ai_key, client_host)
            if ai_access and ai_access.get("allowed"):
                response = await call_next(request)
                record_service_access_event(
                    {
                        "key_id": ai_access.get("key_id", ""),
                        "client_host": client_host,
                        "method": request.method,
                        "path": path,
                        "status_code": response.status_code,
                        "result": "accepted",
                    }
                )
                return response
            status_code = 403 if ai_access and ai_access.get("reason") else 401
            record_service_access_event(
                {
                    "key_id": (ai_access or {}).get("key_id", ""),
                    "client_host": client_host,
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                    "result": (ai_access or {}).get("reason", "invalid_key"),
                }
            )
            return JSONResponse(status_code=status_code, content={"detail": "ai_gateway_key_invalid"})

    token = (
        parse_bearer_token(request.headers.get("Authorization"))
        or request.query_params.get("access_token")
        or request.cookies.get(SESSION_COOKIE_NAME)
    )
    db = None
    try:
        from app.core.database import SessionLocal

        db = SessionLocal()
        user = get_user_by_token(db, token)
        if not user:
            return JSONResponse(status_code=401, content={"detail": "authentication_required"})
    finally:
        if db is not None:
            db.close()

    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    init_database()
    ensure_ai_gateway_bootstrap()
    seed_known_sources()


app.include_router(system_router, prefix="/api/system", tags=["system"])
app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(assets_router, prefix="/api/assets", tags=["assets"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(license_router, prefix="/api/license", tags=["license"])
app.include_router(integrations_router, prefix="/api/integrations", tags=["integrations"])
app.include_router(control_platform_router, prefix="/api/control-platform", tags=["control-platform"])
app.include_router(floor_plan_router, prefix="/api/floor-plans", tags=["floor-plans"])
app.include_router(control_domain_router, prefix="/api/control-domain", tags=["control-domain"])
app.include_router(docs_router, prefix="/api/docs", tags=["docs"])
app.include_router(agent_gateway_router, prefix="/api/agent-gateway", tags=["agent-gateway"])
app.include_router(mobile_router, prefix="/api/mobile", tags=["mobile"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(work_order_router, prefix="/api/work-orders", tags=["work-orders"])
app.include_router(inspection_router, prefix="/api/inspection", tags=["inspection"])
app.include_router(storage_router, prefix="/api/storage", tags=["storage"])
app.include_router(llm_router, prefix="/api/llm", tags=["llm"])
app.include_router(learning_router, prefix="/api/learning", tags=["learning"])
app.include_router(users_router, prefix="/api/users", tags=["users"])
app.include_router(setup_router, prefix="/api/setup", tags=["setup"])
app.include_router(topology_router, prefix="/api/topology", tags=["topology"])

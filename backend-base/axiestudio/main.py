import asyncio
import json
import os
import re
import warnings
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import anyio
import httpx
import sqlalchemy
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from axiestudio.logging import logger
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import PydanticDeprecatedSince20
from pydantic_core import PydanticSerializationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from axiestudio.api import health_check_router, log_router, router
from axiestudio.api.v1.mcp_projects import init_mcp_servers
from axiestudio.initial_setup.setup import (
    create_or_update_starter_projects,
    initialize_super_user_if_needed,
    load_bundles_from_urls,
    load_flows_from_directory,
    sync_flows_from_fs,
)
from axiestudio.interface.components import get_and_cache_all_types_dict
from axiestudio.interface.utils import setup_llm_caching
from axiestudio.logging import configure
from axiestudio.middleware import ContentSizeLimitMiddleware
try:
    from axiestudio.middleware.trial_middleware import TrialMiddleware
    TRIAL_MIDDLEWARE_AVAILABLE = True
except ImportError:
    TRIAL_MIDDLEWARE_AVAILABLE = False
    TrialMiddleware = None

# Import verification middleware
try:
    from axiestudio.middleware.verification_middleware import add_verification_middleware
    VERIFICATION_MIDDLEWARE_AVAILABLE = True
except ImportError:
    VERIFICATION_MIDDLEWARE_AVAILABLE = False

# Import verification scheduler
try:
    from axiestudio.services.verification_scheduler import start_verification_scheduler, stop_verification_scheduler
    VERIFICATION_SCHEDULER_AVAILABLE = True
except ImportError:
    VERIFICATION_SCHEDULER_AVAILABLE = False

# Import subscription setup (will run during startup lifespan)
try:
    from axiestudio.services.startup.subscription_setup import setup_subscription_schema
    SUBSCRIPTION_SETUP_AVAILABLE = True
except ImportError:
    SUBSCRIPTION_SETUP_AVAILABLE = False

# Import enhanced security setup (will run during startup lifespan)
try:
    from axiestudio.services.startup.enhanced_security_setup import initialize_enhanced_security
    ENHANCED_SECURITY_SETUP_AVAILABLE = True
except ImportError:
    ENHANCED_SECURITY_SETUP_AVAILABLE = False
from axiestudio.services.deps import (
    get_queue_service,
    get_settings_service,
    get_telemetry_service,
)
from axiestudio.services.utils import initialize_services, teardown_services

if TYPE_CHECKING:
    from tempfile import TemporaryDirectory

# Ignore Pydantic deprecation warnings from Langchain
warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)

_tasks: list[asyncio.Task] = []

MAX_PORT = 65535


class RequestCancelledMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        sentinel = object()

        async def cancel_handler():
            while True:
                if await request.is_disconnected():
                    return sentinel
                await asyncio.sleep(0.1)

        handler_task = asyncio.create_task(call_next(request))
        cancel_task = asyncio.create_task(cancel_handler())

        done, pending = await asyncio.wait([handler_task, cancel_task], return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        if cancel_task in done:
            return Response("Request was cancelled", status_code=499)
        return await handler_task


class JavaScriptMIMETypeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:
            if isinstance(exc, PydanticSerializationError):
                message = (
                    "Something went wrong while serializing the response. "
                    "Please share this error on our GitHub repository."
                )
                error_messages = json.dumps([message, str(exc)])
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=error_messages) from exc
            raise
        if (
            "files/" not in request.url.path
            and request.url.path.endswith(".js")
            and response.status_code == HTTPStatus.OK
        ):
            response.headers["Content-Type"] = "text/javascript"
        return response


async def load_bundles_with_error_handling():
    try:
        return await load_bundles_from_urls()
    except (httpx.TimeoutException, httpx.HTTPError, httpx.RequestError) as exc:
        logger.error(f"Error loading bundles from URLs: {exc}")
        return [], []


def get_lifespan(*, fix_migration=False, version=None):
    telemetry_service = get_telemetry_service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure()

        # Startup message
        if version:
            logger.debug(f"Starting Axie Studio v{version}...")
        else:
            logger.debug("Starting Axie Studio...")

        temp_dirs: list[TemporaryDirectory] = []
        sync_flows_from_fs_task = None

        try:
            start_time = asyncio.get_event_loop().time()

            logger.debug("Initializing services")
            await initialize_services(fix_migration=fix_migration)
            logger.debug(f"Services initialized in {asyncio.get_event_loop().time() - start_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Setting up LLM caching")
            setup_llm_caching()
            logger.debug(f"LLM caching setup in {asyncio.get_event_loop().time() - current_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Initializing super user")
            await initialize_super_user_if_needed()
            logger.debug(f"Super user initialized in {asyncio.get_event_loop().time() - current_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Loading bundles")
            temp_dirs, bundles_components_paths = await load_bundles_with_error_handling()
            get_settings_service().settings.components_path.extend(bundles_components_paths)
            logger.debug(f"Bundles loaded in {asyncio.get_event_loop().time() - current_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Caching types")
            all_types_dict = await get_and_cache_all_types_dict(get_settings_service())
            logger.debug(f"Types cached in {asyncio.get_event_loop().time() - current_time:.2f}s")

            # Use file-based lock to prevent multiple workers from creating duplicate starter projects concurrently.
            # Note that it's still possible that one worker may complete this task, release the lock,
            # then another worker pick it up, but the operation is idempotent so worst case it duplicates
            # the initialization work.
            current_time = asyncio.get_event_loop().time()
            logger.debug("Creating/updating starter projects")
            import tempfile

            from filelock import FileLock

            lock_file = Path(tempfile.gettempdir()) / "axiestudio_starter_projects.lock"
            lock = FileLock(lock_file, timeout=1)
            try:
                with lock:
                    await create_or_update_starter_projects(all_types_dict)
                    logger.debug(
                        f"Starter projects created/updated in {asyncio.get_event_loop().time() - current_time:.2f}s"
                    )
            except TimeoutError:
                # Another process has the lock
                logger.debug("Another worker is creating starter projects, skipping")
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Failed to acquire lock for starter projects: {e}. Starter projects may not be created or updated."
                )

            current_time = asyncio.get_event_loop().time()
            logger.debug("Starting telemetry service")
            telemetry_service.start()
            logger.debug(f"started telemetry service in {asyncio.get_event_loop().time() - current_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Loading flows")
            await load_flows_from_directory()
            sync_flows_from_fs_task = asyncio.create_task(sync_flows_from_fs())
            queue_service = get_queue_service()
            if not queue_service.is_started():  # Start if not already started
                queue_service.start()
            logger.debug(f"Flows loaded in {asyncio.get_event_loop().time() - current_time:.2f}s")

            current_time = asyncio.get_event_loop().time()
            logger.debug("Loading mcp servers for projects")
            await init_mcp_servers()
            logger.debug(f"mcp servers loaded in {asyncio.get_event_loop().time() - current_time:.2f}s")

            # Set up subscription schema during startup (with timeout protection)
            if SUBSCRIPTION_SETUP_AVAILABLE:
                current_time = asyncio.get_event_loop().time()
                logger.debug("Setting up subscription schema")
                try:
                    # Add timeout to prevent hanging
                    await asyncio.wait_for(setup_subscription_schema(), timeout=30.0)
                    logger.debug(f"Subscription schema setup in {asyncio.get_event_loop().time() - current_time:.2f}s")
                except asyncio.TimeoutError:
                    logger.warning("Subscription schema setup timed out after 30 seconds - continuing startup")
                except Exception as e:
                    logger.warning(f"Subscription schema setup failed: {e} - continuing startup")

            # Set up enhanced security schema during startup (with timeout protection)
            if ENHANCED_SECURITY_SETUP_AVAILABLE:
                current_time = asyncio.get_event_loop().time()
                logger.debug("Setting up enhanced security schema")
                try:
                    # Add timeout to prevent hanging
                    await asyncio.wait_for(initialize_enhanced_security(), timeout=30.0)
                    logger.debug(f"Enhanced security schema setup in {asyncio.get_event_loop().time() - current_time:.2f}s")
                except asyncio.TimeoutError:
                    logger.warning("Enhanced security schema setup timed out after 30 seconds - continuing startup")
                except Exception as e:
                    logger.warning(f"Enhanced security schema setup failed: {e} - continuing startup")

            # Start verification scheduler during startup
            if VERIFICATION_SCHEDULER_AVAILABLE:
                current_time = asyncio.get_event_loop().time()
                logger.debug("Starting verification scheduler")
                try:
                    await start_verification_scheduler()
                    logger.debug(f"Verification scheduler started in {asyncio.get_event_loop().time() - current_time:.2f}s")
                except Exception as e:
                    logger.warning(f"Verification scheduler startup failed: {e} - continuing startup")

            total_time = asyncio.get_event_loop().time() - start_time
            logger.debug(f"Total initialization time: {total_time:.2f}s")
            yield

        except asyncio.CancelledError:
            logger.debug("Lifespan received cancellation signal")
        except Exception as exc:
            if "axiestudio migration --fix" not in str(exc):
                logger.exception(exc)
            raise
        finally:
            # Clean shutdown with progress indicator
            # Create shutdown progress (show verbose timing if log level is DEBUG)
            from axiestudio.__main__ import get_number_of_workers
            from axiestudio.cli.progress import create_axiestudio_shutdown_progress

            log_level = os.getenv("AXIESTUDIO_LOG_LEVEL", "info").lower()
            num_workers = get_number_of_workers(get_settings_service().settings.workers)
            shutdown_progress = create_axiestudio_shutdown_progress(
                verbose=log_level == "debug", multiple_workers=num_workers > 1
            )

            try:
                # Step 0: Stopping Server
                with shutdown_progress.step(0):
                    logger.debug("Stopping server gracefully...")
                    # The actual server stopping is handled by the lifespan context
                    await asyncio.sleep(0.1)  # Brief pause for visual effect

                # Step 1: Cancelling Background Tasks
                with shutdown_progress.step(1):
                    if sync_flows_from_fs_task:
                        sync_flows_from_fs_task.cancel()
                        await asyncio.wait([sync_flows_from_fs_task])

                    # Stop verification scheduler
                    if VERIFICATION_SCHEDULER_AVAILABLE:
                        try:
                            await stop_verification_scheduler()
                            logger.debug("Verification scheduler stopped")
                        except Exception as e:
                            logger.warning(f"Error stopping verification scheduler: {e}")

                # Step 2: Cleaning Up Services
                with shutdown_progress.step(2):
                    try:
                        await asyncio.wait_for(teardown_services(), timeout=10)
                    except asyncio.TimeoutError:
                        logger.warning("Teardown services timed out.")

                # Step 3: Clearing Temporary Files
                with shutdown_progress.step(3):
                    temp_dir_cleanups = [asyncio.to_thread(temp_dir.cleanup) for temp_dir in temp_dirs]
                    await asyncio.gather(*temp_dir_cleanups)

                # Step 4: Finalizing Shutdown
                with shutdown_progress.step(4):
                    logger.debug("Axie Studio shutdown complete")

                # Show completion summary and farewell
                shutdown_progress.print_shutdown_summary()

            except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DBAPIError) as e:
                # Case where the database connection is closed during shutdown
                logger.warning(f"Database teardown failed due to closed connection: {e}")
            except asyncio.CancelledError:
                # Swallow this - it's normal during shutdown
                logger.debug("Teardown cancelled during shutdown.")
            except Exception as e:  # noqa: BLE001
                logger.exception(f"Unhandled error during cleanup: {e}")

            try:
                await asyncio.shield(asyncio.sleep(0.1))  # let logger flush async logs
                await asyncio.shield(logger.complete())
            except asyncio.CancelledError:
                # Cancellation during logger flush is possible during shutdown, so we swallow it
                pass

    return lifespan


def create_app():
    """Create the FastAPI app and include the router."""
    from axiestudio.utils.version import get_version_info

    __version__ = get_version_info()["version"]
    configure()
    lifespan = get_lifespan(version=__version__)
    app = FastAPI(
        title="Axie Studio",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        ContentSizeLimitMiddleware,
    )

    setup_sentry(app)
    origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(JavaScriptMIMETypeMiddleware)

    # Add trial middleware if available
    if TRIAL_MIDDLEWARE_AVAILABLE:
        app.add_middleware(TrialMiddleware)

    # Add verification middleware if available
    if VERIFICATION_MIDDLEWARE_AVAILABLE:
        add_verification_middleware(app)

    @app.middleware("http")
    async def check_boundary(request: Request, call_next):
        if "/api/v1/files/upload" in request.url.path:
            content_type = request.headers.get("Content-Type")

            if not content_type or "multipart/form-data" not in content_type or "boundary=" not in content_type:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Content-Type header must be 'multipart/form-data' with a boundary parameter."},
                )

            boundary = content_type.split("boundary=")[-1].strip()

            if not re.match(r"^[\w\-]{1,70}$", boundary):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Invalid boundary format"},
                )

            body = await request.body()

            boundary_start = f"--{boundary}".encode()
            # The multipart/form-data spec doesn't require a newline after the boundary, however many clients do
            # implement it that way
            boundary_end = f"--{boundary}--\r\n".encode()
            boundary_end_no_newline = f"--{boundary}--".encode()

            if not body.startswith(boundary_start) or not body.endswith((boundary_end, boundary_end_no_newline)):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": "Invalid multipart formatting"},
                )

        return await call_next(request)

    @app.middleware("http")
    async def flatten_query_string_lists(request: Request, call_next):
        flattened: list[tuple[str, str]] = []
        for key, value in request.query_params.multi_items():
            flattened.extend((key, entry) for entry in value.split(","))

        request.scope["query_string"] = urlencode(flattened, doseq=True).encode("utf-8")

        return await call_next(request)

    settings = get_settings_service().settings
    if prome_port_str := os.environ.get("AXIESTUDIO_PROMETHEUS_PORT"):
        # set here for create_app() entry point
        prome_port = int(prome_port_str)
        if prome_port > 0 or prome_port < MAX_PORT:
            logger.debug(f"Starting Prometheus server on port {prome_port}...")
            settings.prometheus_enabled = True
            settings.prometheus_port = prome_port
        else:
            msg = f"Invalid port number {prome_port_str}"
            raise ValueError(msg)

    if settings.prometheus_enabled:
        from prometheus_client import start_http_server

        start_http_server(settings.prometheus_port)

    if settings.mcp_server_enabled:
        from axiestudio.api.v1 import mcp_router

        router.include_router(mcp_router)

    # Add email templates router for testing and management
    from axiestudio.api.v1.email_templates import router as email_templates_router
    router.include_router(email_templates_router)

    app.include_router(router)
    app.include_router(health_check_router)
    app.include_router(log_router)

    @app.exception_handler(Exception)
    async def exception_handler(_request: Request, exc: Exception):
        if isinstance(exc, HTTPException):
            logger.error("HTTPException: %s", str(exc), exc_info=exc)
            return JSONResponse(
                status_code=exc.status_code,
                content={"message": str(exc.detail)},
            )
        logger.error("unhandled error: %s", str(exc), exc_info=exc)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content={"message": str(exc)},
        )

    FastAPIInstrumentor.instrument_app(app)

    add_pagination(app)

    # Mount static files for frontend (when not backend_only)
    settings = get_settings_service().settings
    if not settings.backend_only:
        static_files_dir = get_static_files_dir()
        if static_files_dir and static_files_dir.exists():
            setup_static_files(app, static_files_dir)

    return app


def setup_sentry(app: FastAPI) -> None:
    settings = get_settings_service().settings
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
        )
        app.add_middleware(SentryAsgiMiddleware)


def setup_static_files(app: FastAPI, static_files_dir: Path) -> None:
    """Setup the static files directory.

    Args:
        app (FastAPI): FastAPI app.
        static_files_dir (str): Path to the static files directory.
    """
    app.mount(
        "/",
        StaticFiles(directory=static_files_dir, html=True),
        name="static",
    )

    @app.exception_handler(404)
    async def custom_404_handler(_request, _exc):
        path = anyio.Path(static_files_dir) / "index.html"

        if not await path.exists():
            msg = f"File at path {path} does not exist."
            raise RuntimeError(msg)
        return FileResponse(path)


def get_static_files_dir():
    """Get the static files directory relative to Axie Studio's main.py file."""
    frontend_path = Path(__file__).parent
    return frontend_path / "frontend"


def setup_app(static_files_dir: Path | None = None, *, backend_only: bool = False) -> FastAPI:
    """Setup the FastAPI app."""
    # get the directory of the current file
    if not static_files_dir:
        static_files_dir = get_static_files_dir()

    if not backend_only and (not static_files_dir or not static_files_dir.exists()):
        msg = f"Static files directory {static_files_dir} does not exist."
        raise RuntimeError(msg)
    app = create_app()

    if not backend_only and static_files_dir is not None:
        setup_static_files(app, static_files_dir)
    return app


if __name__ == "__main__":
    import uvicorn

    from axiestudio.__main__ import get_number_of_workers

    configure()
    uvicorn.run(
        "axiestudio.main:create_app",
        host="localhost",
        port=7860,
        workers=get_number_of_workers(),
        log_level="error",
        reload=True,
        loop="asyncio",
    )

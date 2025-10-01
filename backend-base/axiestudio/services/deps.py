from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from axiestudio.logging import logger

from axiestudio.services.schema import ServiceType

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlmodel.ext.asyncio.session import AsyncSession

    from axiestudio.services.cache.service import AsyncBaseCacheService, CacheService
    from axiestudio.services.chat.service import ChatService
    from axiestudio.services.database.service import DatabaseService
    from axiestudio.services.job_queue.service import JobQueueService
    from axiestudio.services.session.service import SessionService
    from axiestudio.services.settings.service import SettingsService
    from axiestudio.services.socket.service import SocketIOService
    from axiestudio.services.state.service import StateService
    from axiestudio.services.storage.service import StorageService
    from axiestudio.services.task.service import TaskService
    from axiestudio.services.telemetry.service import TelemetryService
    from axiestudio.services.tracing.service import TracingService
    from axiestudio.services.variable.service import VariableService


def get_service(service_type: ServiceType, default=None):
    """Retrieves the service instance for the given service type.

    Args:
        service_type (ServiceType): The type of service to retrieve.
        default (ServiceFactory, optional): The default ServiceFactory to use if the service is not found.
            Defaults to None.

    Returns:
        Any: The service instance.

    """
    from axiestudio.services.manager import service_manager

    if not service_manager.factories:
        # ! This is a workaround to ensure that the service manager is initialized
        # ! Not optimal, but it works for now
        service_manager.register_factories()
    return service_manager.get(service_type, default)


def get_telemetry_service() -> TelemetryService:
    """Retrieves the TelemetryService instance from the service manager.

    Returns:
        TelemetryService: The TelemetryService instance.
    """
    from axiestudio.services.telemetry.factory import TelemetryServiceFactory

    return get_service(ServiceType.TELEMETRY_SERVICE, TelemetryServiceFactory())


def get_tracing_service() -> TracingService:
    """Retrieves the TracingService instance from the service manager.

    Returns:
        TracingService: The TracingService instance.
    """
    from axiestudio.services.tracing.factory import TracingServiceFactory

    return get_service(ServiceType.TRACING_SERVICE, TracingServiceFactory())


def get_state_service() -> StateService:
    """Retrieves the StateService instance from the service manager.

    Returns:
        The StateService instance.
    """
    from axiestudio.services.state.factory import StateServiceFactory

    return get_service(ServiceType.STATE_SERVICE, StateServiceFactory())


def get_socket_service() -> SocketIOService:
    """Get the SocketIOService instance from the service manager.

    Returns:
        SocketIOService: The SocketIOService instance.
    """
    return get_service(ServiceType.SOCKETIO_SERVICE)  # type: ignore[attr-defined]


def get_storage_service() -> StorageService:
    """Retrieves the storage service instance.

    Returns:
        The storage service instance.
    """
    from axiestudio.services.storage.factory import StorageServiceFactory

    return get_service(ServiceType.STORAGE_SERVICE, default=StorageServiceFactory())


def get_variable_service() -> VariableService:
    """Retrieves the VariableService instance from the service manager.

    Returns:
        The VariableService instance.

    """
    from axiestudio.services.variable.factory import VariableServiceFactory

    return get_service(ServiceType.VARIABLE_SERVICE, VariableServiceFactory())


def get_settings_service() -> SettingsService:
    """Retrieves the SettingsService instance.

    If the service is not yet initialized, it will be initialized before returning.

    Returns:
        The SettingsService instance.

    Raises:
        ValueError: If the service cannot be retrieved or initialized.
    """
    from axiestudio.services.settings.factory import SettingsServiceFactory

    return get_service(ServiceType.SETTINGS_SERVICE, SettingsServiceFactory())


def get_db_service() -> DatabaseService:
    """Retrieves the DatabaseService instance from the service manager.

    Returns:
        The DatabaseService instance.

    """
    from axiestudio.services.database.factory import DatabaseServiceFactory

    return get_service(ServiceType.DATABASE_SERVICE, DatabaseServiceFactory())


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Retrieves an async session from the database service.

    ENTERPRISE PATTERN: Session without auto-commit for proper transaction control.
    Each endpoint manages its own transaction boundaries explicitly.

    Yields:
        AsyncSession: An async session object for database operations.

    """
    db_service = get_db_service()
    async with db_service.with_session() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for managing an async session scope.

    This context manager is used to manage an async session scope for database operations.
    It ensures that the session is properly committed if no exceptions occur,
    and rolled back if an exception is raised.

    Yields:
        AsyncSession: The async session object.

    Raises:
        Exception: If an error occurs during the session scope.

    """
    db_service = get_db_service()
    async with db_service.with_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.exception("An error occurred during the session scope.")
            await session.rollback()
            raise


def get_cache_service() -> CacheService | AsyncBaseCacheService:
    """Retrieves the cache service from the service manager.

    Returns:
        The cache service instance.
    """
    from axiestudio.services.cache.factory import CacheServiceFactory

    return get_service(ServiceType.CACHE_SERVICE, CacheServiceFactory())


def get_shared_component_cache_service() -> CacheService:
    """Retrieves the cache service from the service manager.

    Returns:
        The cache service instance.
    """
    from axiestudio.services.shared_component_cache.factory import SharedComponentCacheServiceFactory

    return get_service(ServiceType.SHARED_COMPONENT_CACHE_SERVICE, SharedComponentCacheServiceFactory())


def get_session_service() -> SessionService:
    """Retrieves the session service from the service manager.

    Returns:
        The session service instance.
    """
    from axiestudio.services.session.factory import SessionServiceFactory

    return get_service(ServiceType.SESSION_SERVICE, SessionServiceFactory())


def get_task_service() -> TaskService:
    """Retrieves the TaskService instance from the service manager.

    Returns:
        The TaskService instance.

    """
    from axiestudio.services.task.factory import TaskServiceFactory

    return get_service(ServiceType.TASK_SERVICE, TaskServiceFactory())


def get_chat_service() -> ChatService:
    """Get the chat service instance.

    Returns:
        ChatService: The chat service instance.
    """
    return get_service(ServiceType.CHAT_SERVICE)





def get_queue_service() -> JobQueueService:
    """Retrieves the QueueService instance from the service manager."""
    from axiestudio.services.job_queue.factory import JobQueueServiceFactory

    return get_service(ServiceType.JOB_QUEUE_SERVICE, JobQueueServiceFactory())

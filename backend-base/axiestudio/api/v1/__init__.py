from axiestudio.api.v1.api_key import router as api_key_router
from axiestudio.api.v1.axiestudio_store import router as axiestudio_store_router
from axiestudio.api.v1.chat import router as chat_router
from axiestudio.api.v1.email_verification import router as email_verification_router
from axiestudio.api.v1.endpoints import router as endpoints_router
from axiestudio.api.v1.files import router as files_router
from axiestudio.api.v1.flows import router as flows_router
from axiestudio.api.v1.folders import router as folders_router
from axiestudio.api.v1.knowledge_bases import router as knowledge_bases_router
from axiestudio.api.v1.login import router as login_router
from axiestudio.api.v1.mcp import router as mcp_router
from axiestudio.api.v1.mcp_projects import router as mcp_projects_router
from axiestudio.api.v1.monitor import router as monitor_router
from axiestudio.api.v1.openai_responses import router as openai_responses_router
from axiestudio.api.v1.projects import router as projects_router
from axiestudio.api.v1.showcase import router as showcase_router
from axiestudio.api.v1.starter_projects import router as starter_projects_router
from axiestudio.api.v1.subscriptions import router as subscriptions_router
from axiestudio.api.v1.users import router as users_router
from axiestudio.api.v1.validate import router as validate_router
from axiestudio.api.v1.variable import router as variables_router
from axiestudio.api.v1.voice_mode import router as voice_mode_router

__all__ = [
    "api_key_router",
    "axiestudio_store_router",
    "chat_router",
    "email_verification_router",
    "endpoints_router",
    "files_router",
    "flows_router",
    "folders_router",
    "knowledge_bases_router",
    "login_router",
    "mcp_projects_router",
    "mcp_router",
    "monitor_router",
    "openai_responses_router",
    "projects_router",
    "showcase_router",
    "starter_projects_router",
    "subscriptions_router",
    "users_router",
    "validate_router",
    "variables_router",
    "voice_mode_router",
]

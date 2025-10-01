from __future__ import annotations

from typing import TYPE_CHECKING, Any

from axf.components._importing import import_mod

if TYPE_CHECKING:
    from axf.components.data.api_request import APIRequestComponent
    from axf.components.data.csv_to_data import CSVToDataComponent
    from axf.components.data.directory import DirectoryComponent
    from axf.components.data.file import FileComponent
    from axf.components.data.json_to_data import JSONToDataComponent
    from axf.components.data.news_search import NewsSearchComponent
    from axf.components.data.rss import RSSReaderComponent
    from axf.components.data.sql_executor import SQLComponent
    from axf.components.data.url import URLComponent
    from axf.components.data.web_search import WebSearchComponent
    from axf.components.data.webhook import WebhookComponent

_dynamic_imports = {
    "APIRequestComponent": "api_request",
    "CSVToDataComponent": "csv_to_data",
    "DirectoryComponent": "directory",
    "FileComponent": "file",
    "JSONToDataComponent": "json_to_data",
    "NewsSearchComponent": "news_search",
    "RSSReaderComponent": "rss",
    "SQLComponent": "sql_executor",
    "URLComponent": "url",
    "WebSearchComponent": "web_search",
    "WebhookComponent": "webhook",
}

__all__ = [
    "APIRequestComponent",
    "CSVToDataComponent",
    "DirectoryComponent",
    "FileComponent",
    "JSONToDataComponent",
    "NewsSearchComponent",
    "RSSReaderComponent",
    "SQLComponent",
    "URLComponent",
    "WebSearchComponent",
    "WebhookComponent",
]


def __getattr__(attr_name: str) -> Any:
    """Lazily import data components on attribute access."""
    if attr_name not in _dynamic_imports:
        msg = f"module '{__name__}' has no attribute '{attr_name}'"
        raise AttributeError(msg)
    try:
        result = import_mod(attr_name, _dynamic_imports[attr_name], __spec__.parent)
    except (ModuleNotFoundError, ImportError, AttributeError) as e:
        msg = f"Could not import '{attr_name}' from '{__name__}': {e}"
        raise AttributeError(msg) from e
    globals()[attr_name] = result
    return result


def __dir__() -> list[str]:
    return list(__all__)

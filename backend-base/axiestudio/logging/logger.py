import json
import logging
import os
import sys
from collections import deque
from pathlib import Path
from threading import Lock, Semaphore
from typing import TypedDict

import orjson
from loguru import logger
from platformdirs import user_cache_dir
from rich.logging import RichHandler
from typing_extensions import NotRequired, override

from axiestudio.settings import DEV

VALID_LOG_LEVELS = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
# Human-readable
DEFAULT_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <level>{level: <8}</level> - {module} - <level>{message}</level>"
)


class SizedLogBuffer:
    def __init__(
        self,
        max_readers: int = 20,  # max number of concurrent readers for the buffer
    ):
        """A buffer for storing log messages for the log retrieval API.

        The buffer can be overwritten by an env variable AXIESTUDIO_LOG_RETRIEVER_BUFFER_SIZE
        because the logger is initialized before the settings_service are loaded.
        """
        self.buffer: deque = deque()

        self._max_readers = max_readers
        self._wlock = Lock()
        self._rsemaphore = Semaphore(max_readers)
        self._max = 0

    def get_write_lock(self) -> Lock:
        return self._wlock

    def write(self, message: str) -> None:
        record = json.loads(message)
        log_entry = record["text"]
        epoch = int(record["record"]["time"]["timestamp"] * 1000)
        with self._wlock:
            if len(self.buffer) >= self.max:
                self.buffer.popleft()
            self.buffer.append({"timestamp": epoch, "message": log_entry})

    def read(self) -> list[dict]:
        with self._rsemaphore:
            return list(self.buffer)

    def clear(self) -> None:
        with self._wlock:
            self.buffer.clear()

    def __len__(self) -> int:
        return len(self.buffer)

    def __bool__(self) -> bool:
        return len(self.buffer) > 0

    def __iter__(self):
        return iter(self.buffer)

    def __getitem__(self, index):
        return self.buffer[index]

    def __setitem__(self, index, value):
        self.buffer[index] = value

    def __delitem__(self, index):
        del self.buffer[index]

    def __contains__(self, item):
        return item in self.buffer

    def __reversed__(self):
        return reversed(self.buffer)

    def append(self, item):
        with self._wlock:
            if len(self.buffer) >= self.max:
                self.buffer.popleft()
            self.buffer.append(item)

    def appendleft(self, item):
        with self._wlock:
            if len(self.buffer) >= self.max:
                self.buffer.pop()
            self.buffer.appendleft(item)

    def pop(self):
        with self._wlock:
            return self.buffer.pop()

    def popleft(self):
        with self._wlock:
            return self.buffer.popleft()

    def extend(self, iterable):
        with self._wlock:
            for item in iterable:
                if len(self.buffer) >= self.max:
                    self.buffer.popleft()
                self.buffer.append(item)

    def extendleft(self, iterable):
        with self._wlock:
            for item in iterable:
                if len(self.buffer) >= self.max:
                    self.buffer.pop()
                self.buffer.appendleft(item)

    @property
    def max(self) -> int:
        # Get it dynamically to allow for env variable changes
        if self._max == 0:
            env_buffer_size = os.getenv("AXIESTUDIO_LOG_RETRIEVER_BUFFER_SIZE", "0")
            if env_buffer_size.isdigit():
                self._max = int(env_buffer_size)
        return self._max

    @max.setter
    def max(self, value: int) -> None:
        self._max = value

    def enabled(self) -> bool:
        return self.max > 0

    def max_size(self) -> int:
        return self.max


# log buffer for capturing log messages
log_buffer = SizedLogBuffer()


def serialize_log(record):
    subset = {
        "timestamp": record["time"].timestamp(),
        "message": record["message"],
        "level": record["level"].name,
        "module": record["module"],
    }
    return orjson.dumps(subset)


class InterceptHandler(logging.Handler):
    @override
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def is_valid_log_format(log_format: str) -> bool:
    """Check if the log format is valid."""
    try:
        # Try to format a test record
        test_record = {
            "time": "2023-01-01 00:00:00",
            "level": "INFO",
            "module": "test",
            "message": "test message",
        }
        log_format.format(**test_record)
        return True
    except (KeyError, ValueError):
        return False


def patching(record) -> None:
    record["extra"]["serialized"] = serialize_log(record)
    if DEV is False:
        record.pop("exception", None)


class LogConfig(TypedDict):
    log_level: NotRequired[str]
    log_file: NotRequired[Path]
    disable: NotRequired[bool]
    log_env: NotRequired[str]
    log_format: NotRequired[str]


def configure(
    *,
    log_level: str | None = None,
    log_file: Path | None = None,
    disable: bool | None = False,
    log_env: str | None = None,
    log_format: str | None = None,
    async_file: bool = False,
    log_rotation: str | None = None,
) -> None:
    if disable and log_level is None and log_file is None:
        logger.disable("axiestudio")
    if os.getenv("AXIESTUDIO_LOG_LEVEL", "").upper() in VALID_LOG_LEVELS and log_level is None:
        log_level = os.getenv("AXIESTUDIO_LOG_LEVEL")
    if log_level is None:
        log_level = "ERROR"

    if log_file is None:
        env_log_file = os.getenv("AXIESTUDIO_LOG_FILE", "")
        log_file = Path(env_log_file) if env_log_file else None

    if log_env is None:
        log_env = os.getenv("AXIESTUDIO_LOG_ENV", "")

    # Get log format from env if not provided
    if log_format is None:
        log_format = os.getenv("AXIESTUDIO_LOG_FORMAT")

    logger.remove()
    logger.add(sink=patching, format="{message}", level="TRACE", serialize=False)

    if not disable:
        if log_format is None or not is_valid_log_format(log_format):
            log_format = DEFAULT_LOG_FORMAT
        # pretty print to rich stdout development-friendly but poor performance, It's better for debugger.
        # suggest directly print to stdout in production
        log_stdout_pretty = os.getenv("AXIESTUDIO_PRETTY_LOGS", "true").lower() == "true"
        if log_stdout_pretty:
            logger.configure(
                handlers=[
                    {
                        "sink": RichHandler(rich_tracebacks=True, markup=True),
                        "format": log_format,
                        "level": log_level.upper(),
                    }
                ]
            )
        else:
            logger.add(sys.stdout, level=log_level.upper(), format=log_format, backtrace=True, diagnose=True)

        if not log_file:
            cache_dir = Path(user_cache_dir("axiestudio"))
            logger.debug(f"Cache directory: {cache_dir}")
            log_file = cache_dir / "axiestudio.log"
            logger.debug(f"Log file: {log_file}")

        if os.getenv("AXIESTUDIO_LOG_ROTATION") and log_rotation is None:
            log_rotation = os.getenv("AXIESTUDIO_LOG_ROTATION")
        elif log_rotation is None:
            log_rotation = "1 day"

        try:
            logger.add(
                sink=log_file,
                level=log_level.upper(),
                format=log_format,
                serialize=True,
                enqueue=async_file,
                rotation=log_rotation,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Error setting up log file")

    if log_buffer.enabled():
        logger.add(sink=log_buffer.write, format="{time} {level} {message}", serialize=True)

    logger.debug(f"Logger set up with log level: {log_level}")

    setup_uvicorn_logger()
    setup_gunicorn_logger()


def setup_uvicorn_logger() -> None:
    loggers = (logging.getLogger(name) for name in logging.root.manager.loggerDict if name.startswith("uvicorn."))
    for uvicorn_logger in loggers:
        uvicorn_logger.handlers = []
    logging.getLogger("uvicorn").handlers = [InterceptHandler()]


def setup_gunicorn_logger() -> None:
    logging.getLogger("gunicorn.error").handlers = [InterceptHandler()]
    logging.getLogger("gunicorn.access").handlers = [InterceptHandler()]


def get_log_buffer() -> SizedLogBuffer:
    return log_buffer


def get_logs() -> list[dict]:
    return log_buffer.read()


def clear_logs() -> None:
    log_buffer.clear()


def set_log_buffer_size(size: int) -> None:
    log_buffer.max = size

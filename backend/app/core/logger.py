"""
Logging setup — structlog use karta hai agar available ho,
warna standard Python logging pe fallback karta hai.
Ye ensure karta hai ki app structlog ke bina bhi chale.
"""

import logging
import sys

# ── Try structlog ─────────────────────────────────────────────────────────────
try:
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            # add_logger_name removed — PrintLoggerFactory has no .name attribute
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    def get_logger(name: str):
        return structlog.get_logger(name)

    _USING_STRUCTLOG = True

except ImportError:
    # structlog not installed — use standard logging
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    class _StdLogWrapper:
        """Minimal wrapper that mimics structlog's bound-logger API."""

        def __init__(self, name: str):
            self._log = logging.getLogger(name)

        def _fmt(self, event: str, **kw) -> str:
            if kw:
                parts = " ".join(f"{k}={v!r}" for k, v in kw.items())
                return f"{event} {parts}"
            return event

        def debug(self, event: str, **kw):
            self._log.debug(self._fmt(event, **kw))

        def info(self, event: str, **kw):
            self._log.info(self._fmt(event, **kw))

        def warning(self, event: str, **kw):
            self._log.warning(self._fmt(event, **kw))

        def warn(self, event: str, **kw):
            self.warning(event, **kw)

        def error(self, event: str, **kw):
            self._log.error(self._fmt(event, **kw))

        def critical(self, event: str, **kw):
            self._log.critical(self._fmt(event, **kw))

        def exception(self, event: str, **kw):
            self._log.exception(self._fmt(event, **kw))

        def bind(self, **kw):
            return self

    def get_logger(name: str) -> _StdLogWrapper:
        return _StdLogWrapper(name)

    _USING_STRUCTLOG = False

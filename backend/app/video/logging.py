"""Never write reference signatures or temporary media tokens into access logs."""
import logging
import re


class VideoURLFilter(logging.Filter):
    def filter(self, record):
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).startswith("/api/videos/assets/public/"):
                args[2] = str(args[2]).split("?", 1)[0]
                record.args = tuple(args)
        if record.name in ("httpx", "httpcore"):
            message = record.getMessage()
            record.msg = re.sub(r"(https://[^\s?\"]+)\?[^\s\"]+", r"\1?[redacted]", message)
            record.args = ()
        return True


def install_video_log_filter():
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, VideoURLFilter) for f in logger.filters):
            logger.addFilter(VideoURLFilter())

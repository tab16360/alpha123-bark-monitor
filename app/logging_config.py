import logging
import re
import sys

class SensitiveDataFilter(logging.Filter):
    """Filter to mask Bark device key or tokens from logs."""

    # Matches Bark URLs like https://api.day.app/YOUR_KEY or /push with device_key
    KEY_REGEX = re.compile(r"(https?://[^/]+/)([a-zA-Z0-9_\-]{10,})")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.KEY_REGEX.sub(r"\1*****", record.msg)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self.KEY_REGEX.sub(r"\1*****", arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True


def setup_logging(level_name: str = "INFO") -> logging.Logger:
    """Configure application logging."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("alpha_monitor")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    logger.addHandler(handler)
    logger.propagate = False
    return logger

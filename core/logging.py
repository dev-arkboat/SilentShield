"""Anonymity-safe logging filter: drops IP-like fields if ever attached."""

import logging


class NoIPFilter(logging.Filter):
    BLOCKED = ("REMOTE_ADDR", "HTTP_X_FORWARDED_FOR", "HTTP_USER_AGENT", "ip", "ip_address")

    def filter(self, record: logging.LogRecord) -> bool:
        for key in self.BLOCKED:
            if hasattr(record, key):
                try:
                    delattr(record, key)
                except Exception:
                    pass
        return True

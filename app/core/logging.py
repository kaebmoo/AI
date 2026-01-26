import logging
import json
import re
from contextvars import ContextVar
from typing import Optional

# Context variable for request tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class PIIRedactingFormatter(logging.Formatter):
    """Formatter that redacts PII from log messages"""
    
    PII_PATTERNS = [
        (r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL_REDACTED]'),
        (r'\b\d{10}\b', '[PHONE_REDACTED]'),
        (r'\b\d{13}\b', '[ID_CARD_REDACTED]'),
        (r'password["\']?\s*[:=]\s*["\']?[^"\'\\s]+', 'password=[REDACTED]'),
        (r'token["\']?\s*[:=]\s*["\']?[^"\'\s]+', 'token=[REDACTED]'),
        (r'otp["\']?\s*[:=]\s*["\']?\d+', 'otp=[REDACTED]'),
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        
        for pattern, replacement in self.PII_PATTERNS:
            message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
        
        return message

class StructuredLogFormatter(PIIRedactingFormatter):
    """JSON structured logging with request_id correlation"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Get request_id from context
        request_id = request_id_var.get()
        
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data["extra"] = record.extra_data
        
        formatted = json.dumps(log_data, ensure_ascii=False)
        
        # Apply PII redaction
        for pattern, replacement in self.PII_PATTERNS:
            formatted = re.sub(pattern, replacement, formatted, flags=re.IGNORECASE)
        
        return formatted

def setup_logging():
    """Configure application logging"""
    
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredLogFormatter())
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    
    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

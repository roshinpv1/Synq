import logging
import json
import datetime
import contextvars

# Contextvar to store the request-scoped trace ID (Correlation ID)
request_trace_id = contextvars.ContextVar("request_trace_id", default=None)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "filename": record.filename,
            "line": record.lineno
        }
        
        # Automatically inject request trace ID if active in context
        trace_id = request_trace_id.get()
        if trace_id:
            log_data["trace_id"] = trace_id
        elif hasattr(record, "trace_id") and record.trace_id:
            log_data["trace_id"] = record.trace_id
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers to avoid double printing
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(stream_handler)

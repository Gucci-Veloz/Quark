import logging
import sys
import time
import json
from typing import Callable, Dict, Any, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Configurar el logger
logger = logging.getLogger("quark")
logger.setLevel(logging.INFO)

# Formateador que incluye el timestamp
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Handler para la consola
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

try:
    # Handler para un archivo de log
    file_handler = logging.FileHandler("logs/quark.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except FileNotFoundError:
    # Si el directorio de logs no existe, lo creamos
    import os
    os.makedirs("logs", exist_ok=True)
    # Intentamos de nuevo
    try:
        file_handler = logging.FileHandler("logs/quark.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"No se pudo crear el archivo de log: {e}")

_SENSITIVE_HEADERS = {"x-api-key", "authorization", "cookie", "set-cookie", "proxy-authorization"}
_SENSITIVE_MARKERS = ("token", "secret", "key", "password")


def redact_headers(headers) -> Dict[str, str]:
    """Copia de los headers con los valores sensibles reemplazados por [REDACTED]."""
    out = {}
    for name, value in dict(headers).items():
        low = name.lower()
        if low in _SENSITIVE_HEADERS or any(m in low for m in _SENSITIVE_MARKERS):
            out[name] = "[REDACTED]"
        else:
            out[name] = value
    return out


class CustomJSONEncoder(json.JSONEncoder):
    """
    Encoder personalizado para manejar tipos no serializables por defecto.
    """
    def default(self, obj):
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def _serialize_context(context: Optional[Dict[str, Any]]) -> str:
    """
    Serializa el contexto para incluirlo en el log.
    """
    if not context:
        return ""
    
    try:
        return " | " + json.dumps(context, cls=CustomJSONEncoder)
    except Exception:
        return " | " + str(context)

# Clase para el manejo contextual de logs
class ContextLogger:
    def __init__(self, logger_instance):
        self._logger = logger_instance
        # Guardar referencia a los métodos originales
        self._original_debug = logger_instance.debug
        self._original_info = logger_instance.info
        self._original_warning = logger_instance.warning
        self._original_error = logger_instance.error
        self._original_critical = logger_instance.critical

    def debug(self, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
        context_str = _serialize_context(context) if context else ""
        self._original_debug(f"{msg}{context_str}")

    def info(self, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
        context_str = _serialize_context(context) if context else ""
        self._original_info(f"{msg}{context_str}")

    def warning(self, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
        context_str = _serialize_context(context) if context else ""
        self._original_warning(f"{msg}{context_str}")

    def error(self, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
        context_str = _serialize_context(context) if context else ""
        self._original_error(f"{msg}{context_str}")

    def critical(self, msg: str, context: Optional[Dict[str, Any]] = None) -> None:
        context_str = _serialize_context(context) if context else ""
        self._original_critical(f"{msg}{context_str}")

# Crear una instancia del logger contextual
context_logger = ContextLogger(logger)

# Reemplazar los métodos del logger con los de nuestro wrapper
logger.debug = context_logger.debug
logger.info = context_logger.info
logger.warning = context_logger.warning
logger.error = context_logger.error
logger.critical = context_logger.critical

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware para registrar información sobre cada solicitud y respuesta.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Extraer información de la solicitud
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        url = str(request.url)
        
        # Registrar la solicitud
        logger.info(
            f"Solicitud recibida: {method} {url}",
            {
                "client_ip": client_host,
                "method": method,
                "url": url,
                "headers": redact_headers(request.headers)
            }
        )
        
        try:
            # Procesar la solicitud
            response = await call_next(request)
            
            # Calcular el tiempo de respuesta
            process_time = time.time() - start_time
            
            # Registrar la respuesta
            logger.info(
                f"Respuesta enviada: {response.status_code}",
                {
                    "status_code": response.status_code,
                    "process_time_ms": round(process_time * 1000, 2),
                    "content_type": response.headers.get("content-type", "")
                }
            )
            
            return response
        except Exception as exc:
            # Registrar la excepción
            process_time = time.time() - start_time
            logger.error(
                f"Error procesando solicitud: {str(exc)}",
                {
                    "exception": type(exc).__name__,
                    "process_time_ms": round(process_time * 1000, 2),
                    "client_ip": client_host,
                    "method": method,
                    "url": url
                }
            )
            raise 
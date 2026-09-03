import os
import sys
import traceback

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.config import API_TITLE, API_DESCRIPTION, API_VERSION, get_settings
from app.utils.logger import LoggingMiddleware, logger

# Verificar importaciones de módulos
try:
    from app.modules import identity, business, reminders, connections, learnings, priorities, suggestions, airtable, external
except ImportError as e:
    logger.critical(f"Error al importar módulos: {e}")
    sys.exit(1)

from app.utils.auth import Token, create_access_token, validate_access, validate_scope, get_password_hash, verify_password

# Crear la aplicación FastAPI
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Obtener la configuración desde las variables de entorno
settings = get_settings()

# Configurar CORS basado en la configuración
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=settings.allowed_methods,
    allow_headers=settings.allowed_headers,
)

# Añadir middleware de logging
app.add_middleware(LoggingMiddleware)

# Incluir los routers de los módulos con protección de autenticación
# Nota: no requerimos autenticación para el acceso a la documentación (/docs y /redoc)

# Módulo de identidad y psicología
app.include_router(identity.router)

# Módulo de negocios y estrategia
app.include_router(business.router)

# Módulo de recordatorios y URLs
app.include_router(reminders.router)

# Módulo de conexiones inteligentes
app.include_router(connections.router)

# Módulo de aprendizajes y reflexiones
app.include_router(learnings.router)

# Módulo de priorización y filtrado
app.include_router(priorities.router)

# Módulo de sugerencias inteligentes
app.include_router(suggestions.router)

# Módulo de integración con Airtable
app.include_router(airtable.router)

# Módulo de acceso externo a QUARK
app.include_router(external.router)

# Endpoint para autenticación
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Obtiene un token de acceso JWT.
    """
    # En un sistema real, se debería verificar contra una base de datos
    # Por ahora, comprobamos contra la contraseña almacenada en settings
    admin_password = settings.admin_password
    
    if not admin_password:
        logger.error("Contraseña de administrador no configurada.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error en el servidor"
        )
    
    # En un sistema real, obtendríamos el hash almacenado en la base de datos
    # Aquí, como no tenemos base de datos, simulamos que ya tenemos el hash
    # En producción, NUNCA deberías almacenar contraseñas en texto plano
    if form_data.username != "admin" or form_data.password != admin_password:
        logger.warning("Intento de autenticación fallido", {"username": form_data.username})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generar token JWT
    access_token = create_access_token(
        data={"sub": form_data.username, "scopes": ["read", "write"]}
    )
    
    logger.info("Inicio de sesión exitoso", {"username": form_data.username})
    
    return {"access_token": access_token, "token_type": "bearer"}

# Ruta raíz
@app.get("/")
async def root():
    """
    Ruta raíz que proporciona información básica sobre la API.
    """
    return {
        "name": API_TITLE,
        "description": API_DESCRIPTION,
        "version": API_VERSION,
        "documentation": "/docs",
        "modules": [
            {"name": "Identidad y Psicología", "endpoint": "/identity"},
            {"name": "Negocios y Estrategia", "endpoint": "/business"},
            {"name": "Recordatorios y URLs", "endpoint": "/reminders"},
            {"name": "Conexiones Inteligentes", "endpoint": "/connections"},
            {"name": "Aprendizajes y Reflexiones", "endpoint": "/learnings"},
            {"name": "Priorización y Filtrado", "endpoint": "/priorities"},
            {"name": "Sugerencias Inteligentes", "endpoint": "/suggestions"},
            {"name": "Integración con Airtable", "endpoint": "/airtable"},
            {"name": "Acceso externo a QUARK", "endpoint": "/external"}
        ]
    }

# Endpoint protegido para verificar autenticación
@app.get("/check-auth")
async def check_auth(user = Depends(validate_access)):
    """
    Verifica si el usuario está autenticado correctamente.
    """
    return {
        "authenticated": True,
        "user_info": user
    }

# Endpoint para verificar permisos de escritura
@app.get("/check-write-permission")
async def check_write_permission(user = Depends(validate_scope("write"))):
    """
    Verifica si el usuario tiene permisos de escritura.
    """
    return {
        "authorized": True,
        "scope": "write",
        "user_info": user
    }

# Manejador de excepciones global
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Manejador global de excepciones.
    """
    # Registrar la excepción con stack trace
    logger.error(f"Error no manejado: {str(exc)}", {
        "error_type": type(exc).__name__, 
        "traceback": traceback.format_exc(),
        "path": request.url.path
    })
    
    # Devolver una respuesta de error genérica
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"}
    )

# Manejador de excepciones HTTP
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Manejador de excepciones HTTP.
    """
    logger.warning(f"HTTP Exception: {exc.detail}", {
        "status_code": exc.status_code,
        "path": request.url.path
    })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Punto de entrada para ejecutar la aplicación con uvicorn
if __name__ == "__main__":
    import uvicorn
    host = settings.host
    port = settings.port
    reload_option = settings.reload
    log_level = settings.log_level.lower()
    
    logger.info(f"Iniciando servidor QUARK en {host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_option, log_level=log_level)
import os
from dotenv import load_dotenv
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Cargar variables de entorno
load_dotenv()

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Configuración de la API
API_TITLE = "QUARK"
API_DESCRIPTION = "API para almacenar y recuperar información estructurada"
API_VERSION = "0.1.0"

# Clase Settings para manejar la configuración desde variables de entorno
class Settings(BaseSettings):
    # Configuración del servidor
    host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    port: int = Field(default=8080, validation_alias="API_PORT")
    reload: bool = Field(default=True, validation_alias="API_RELOAD")
    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")
    
    # Configuración de seguridad
    # Sin default: si ADMIN_PASSWORD no está seteada en el entorno, Settings()
    # falla al instanciarse (arranque de la app), en vez de admitir en silencio
    # una contraseña fija conocida por cualquiera que lea el repo.
    admin_password: str = Field(..., validation_alias="ADMIN_PASSWORD")
    auth_secret_key: str = Field(default="insecure_default_key_change_in_production", validation_alias="AUTH_SECRET_KEY")
    auth_algorithm: str = Field(default="HS256", validation_alias="AUTH_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Configuración de CORS
    allowed_origins: list[str] = Field(default=["*"], validation_alias="ALLOWED_ORIGINS")
    allow_credentials: bool = Field(default=True, validation_alias="ALLOW_CREDENTIALS")
    allowed_methods: list[str] = Field(default=["*"], validation_alias="ALLOWED_METHODS")
    allowed_headers: list[str] = Field(default=["*"], validation_alias="ALLOWED_HEADERS")
    
    # Configuración de ChromaDB
    chroma_db_dir: str = Field(default=str(BASE_DIR / "data" / "chroma"), validation_alias="CHROMA_DB_DIR")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL")
    
    # Configuración de Airtable
    airtable_api_key: str = Field(default="", validation_alias="AIRTABLE_API_KEY")
    airtable_base_id: str = Field(default="", validation_alias="AIRTABLE_BASE_ID")
    airtable_table_id: str = Field(default="tbln3teMfz1sbqIuf", validation_alias="AIRTABLE_TABLE_ID")
    
    # API Key para acceso externo a QUARK
    quark_api_key: str = Field(default="", validation_alias="QUARK_API_KEY")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )

# Función para obtener la configuración
def get_settings():
    return Settings()

# Configuración de ChromaDB
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", str(BASE_DIR / "data" / "chroma"))

# Configuración de embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Nombres de las colecciones en ChromaDB
COLLECTIONS = {
    "identity": "identity_psychology",
    "business": "business_strategy",
    "reminders": "reminders_urls",
    "connections": "smart_connections",
    "learnings": "learnings_reflections",
    "priorities": "priority_filtering",
    "suggestions": "smart_suggestions"
} 

# Configuración de Airtable
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID", "tbln3teMfz1sbqIuf")

# Configuración de seguridad
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "insecure_default_key_change_in_production")
AUTH_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# API Key para acceso externo a QUARK
QUARK_API_KEY = os.getenv("QUARK_API_KEY")
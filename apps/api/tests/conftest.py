import os
import base64

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://promptguard:promptguard@localhost:5432/promptguard")
os.environ.setdefault("PROMPTGUARD_TEMP_FILE_ENCRYPTION_KEY", base64.b64encode(b"T" * 32).decode())

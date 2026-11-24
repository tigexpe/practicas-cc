import os
import sys
from pathlib import Path

# Requiere DATABASE_URL apuntando a un Postgres de pruebas. Sin Redis por defecto.
os.environ.setdefault("REDIS_URL", "")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

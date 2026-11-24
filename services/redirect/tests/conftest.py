import os
import sys
from pathlib import Path

# Sin Redis por defecto (debe fijarse antes de importar la app).
os.environ.setdefault("REDIS_URL", "")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

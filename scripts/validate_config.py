from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.config import load_config

config = load_config()
print(f"OK: {config.name} {config.version}")
print(f"Databases: {', '.join(config.databases)}")
print(f"Resources: {len(config.resources)}")
for resource in config.resources:
    print(f"- {resource.path} -> {resource.database}:{resource.table}")

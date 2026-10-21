"""Export the exact schema exposed by FastAPI; run from the repository root."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.main import app

output=ROOT/'docs'/'openapi.json'
output.write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Exported {output}')

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extractors.arc import extract_profile

path = sys.argv[1] if len(sys.argv) > 1 else "../seed/arc_front.png"
doc_type = sys.argv[2] if len(sys.argv) > 2 else "arc_front"

data = Path(path).read_bytes()
result = extract_profile(data, doc_type, ext=Path(path).suffix)

print(json.dumps(result, ensure_ascii=False, indent=2))
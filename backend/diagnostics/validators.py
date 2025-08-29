import ast, re
from typing import Tuple, Dict, Any, List
from core.models import ValidationMessage
from core.security import static_scan

def static_validate(code: str) -> Tuple[List[ValidationMessage], Dict[str, Any]]:
    msgs: List[ValidationMessage] = []
    try:
        ast.parse(code)
    except SyntaxError as e:
        msgs.append(ValidationMessage(level="error", message=f"SyntaxError: {e}", line=e.lineno))
        return msgs, {}
    for pat, line in static_scan(code):
        msgs.append(ValidationMessage(level="error", message=f"disallowed pattern: {pat}", line=line))
    inferred = {"fluid": None, "junctions": [], "pipes": []}
    # naive heuristics
    if re.search(r"create_junction", code): inferred["junctions"].append("j")
    if re.search(r"create_pipe", code): inferred["pipes"].append("p")
    if re.search(r"hydrogen", code.lower()): inferred["fluid"]="hydrogen"
    return msgs, inferred
import json
import re


def parse_json(text: str):
    """Tolerant JSON parse: strips code fences and surrounding prose."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"(\[.*\]|\{.*\})", t, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(1))

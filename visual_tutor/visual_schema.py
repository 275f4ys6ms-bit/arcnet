import re

TAG_RE = re.compile(
    r"\[\[VISUAL:\s*([a-zA-Z_]+)\s*(?:\|\s*([^|\]]+?)\s*)?(?:\|\s*([^\]]+?)\s*)?\]\]"
)

COLORS = {
    "red": "#ef5350", "green": "#66bb6a", "blue": "#42a5f5",
    "yellow": "#ffee58", "orange": "#ffa726", "white": "#eceff1",
    "black": "#212121", "purple": "#ab47bc",
}


def parse_tag(raw):
    match = TAG_RE.fullmatch(raw.strip())
    if not match:
        return None
    return {"action": match.group(1), "object": match.group(2) or "concept",
            "attributes": match.group(3) or ""}


def _attrs(attr_str):
    attrs = {}
    for token in (attr_str or "").split(","):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            attrs[key.strip()] = value.strip()
        else:
            attrs[token] = True
    return attrs


def expand(action, obj, attr_str=""):
    attrs = _attrs(attr_str)
    color = next((COLORS[key] for key in attrs if key in COLORS), None)
    if action == "erase":
        wipe = attrs.get("all") or obj in ("canvas", "all")
        return {"op": "erase", "id": "*" if wipe else obj}
    if action == "highlight":
        return {"op": "highlight", "id": obj, "color": color or "#ffee58"}
    if action == "animate":
        motion = attrs.get("motion") or ("rays" if attrs.get("rays") else "pulse")
        return {"op": "animate", "id": obj, "motion": motion,
                "dx": int(attrs.get("dx", 0)), "dy": int(attrs.get("dy", 12)),
                "dur": int(attrs.get("dur", 1200))}
    shape = attrs.get("shape")
    if not shape:
        name = obj.lower()
        if "arrow" in name or attrs.get("into") or attrs.get("out"):
            shape = "arrow"
        elif any(word in name for word in ("sun", "circle", "wheel")):
            shape = "circle"
        elif any(word in name for word in ("cell", "leaf", "glucose", "hexagon", "plant")):
            shape = "ellipse"
        elif any(word in name for word in ("text", "label", "caption", "title")):
            shape = "label"
        else:
            shape = "rect"
    command = {"op": "draw", "id": obj, "shape": shape,
               "fill": color or "#eceff1", "stroke": color or "#eceff1"}
    if shape == "label":
        command["text"] = str(attrs.get("text", obj.replace("_", " ")))
    elif "text" in attrs:
        command["text"] = str(attrs["text"])
    return command

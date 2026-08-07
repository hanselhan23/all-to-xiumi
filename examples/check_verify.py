import json, sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

resp = json.loads(data["editingResp"])
layer = resp["cubes"][0]["pages"][0]["layers"][0]
items = layer["comps"]["items"]
print(f"comp count: {len(items)}")

BLUE = ["#2A7696", "#1D5A78", "#7FB6CD", "#A9C9D9", "#EAF3F7", "#DBEAF2", "#7A9AAB", "#3A4A54", "#D7E9F2"]
ORANGE = ["#C05A2E", "#A23E24", "#D6A98E", "#F6ECE4", "#F7E4D3", "#B08A6F", "#B08366", "#4A3B32"]
YELLOW = ["#E3A524", "#BE8413", "#F3CD7C", "#E2C787", "#FBF3DF", "#F6E6C0", "#B3946B", "#4F4538", "#FBF0D8"]

def css_text(txt1):
    style = txt1.get("style") or {}
    s = "".join(f"{k}:{v};" for k, v in style.items())
    return s + " " + (txt1.get("text") or "")

def has_color(blob, c):
    return c.lower() in blob.lower()

for i, c in enumerate(items):
    txt1 = c.get("txt1") or {}
    style = txt1.get("style") or {}
    s = css_text(txt1)
    grad = "linear-gradient" in s
    yellow_hits = [c for c in YELLOW if has_color(s, c)]
    other_hits = [c for c in BLUE + ORANGE if has_color(s, c)]
    text_head = " ".join((txt1.get("text") or "").replace("</p>", " ").replace("<br>", " ").replace("</span>", " ").split())[:24]
    print(f"[{i}] grad={grad} yellow={yellow_hits} other={other_hits} | {text_head}")

all_blob = "\n".join(css_text(c.get("txt1") or {}) for c in items)
leftover = [c for c in BLUE + ORANGE if c.lower() in all_blob.lower()]
print("\nLEFTOVER OLD COLORS:", leftover if leftover else "none")

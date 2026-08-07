import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)

resp = json.loads(data["editingResp"])
layer = resp["cubes"][0]["pages"][0]["layers"][0]
items = layer["comps"]["items"]
print(f"comp count: {len(items)}")

t = items[0]["txt1"]
style = t.get("style") or {}
text = t.get("text") or ""

print("--- comp[0] style ---")
for k, v in style.items():
    print(f"  {k}: {v}")

print("--- comp[0] text checks ---")
print("  has cdn img:", "img.xiumi.us" in text)
print("  has art title:", "物理迎新志愿者招募" in text)
print("  has 38px:", "font-size:38px" in text)
print("  has text-shadow:", "text-shadow" in text)
print("  has 18px copy:", "font-size:18px" in text)
print("  has heiti:", ("黑体" in text or "Microsoft YaHei" in text))
print("  has line-effect:", "linear-gradient(90deg,rgba(255,255,255,0)" in text)
print("  has TSINGHUA:", "TSINGHUA" in text)

all_text = " ".join((c.get("txt1") or {}).get("text", "") for c in items)
print("--- global checks ---")
print("  封面占位残留:", "封面图占位" in all_text)
print("  引言第一段残留:", "还记得自己刚踏入清华园时的样子吗？" in all_text and "TSINGHUA" not in all_text)
print("  logo 相对路径残留:", "物理系logo.png" in all_text)
print("  img 总数:", all_text.count("<img"))

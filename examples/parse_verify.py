import json
import re
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
m = re.search(r'"editingResp":\s*("(?:[^"\\]|\\.)*")', text)
if not m:
    print("NO_MATCH")
    sys.exit(0)
resp = json.loads(m.group(1))
cubes = resp.get("cubes") or []
pages = (cubes[0].get("pages") or []) if cubes else []
layers = (pages[0].get("layers") or []) if pages else []
comps = (layers[0].get("comps") or {}).get("items") or []
print("COMP_COUNT=%d" % len(comps))
for i, cp in enumerate(comps):
    txt = cp.get("txt1")
    if not txt:
        continue
    print("--COMP%d--" % i)
    print("TEXT=%s" % txt.get("text", ""))
    print("STYLE=%s" % json.dumps(txt.get("style"), ensure_ascii=False))
qiblock = (layers[0].get("_qiBlock") or {}).get("items") or []
print("QIBLOCK_COUNT=%d" % len(qiblock))

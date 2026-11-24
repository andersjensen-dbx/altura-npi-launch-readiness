import json, sys
nb = json.load(open(sys.argv[1]))
for c in nb["cells"]:
    for o in c.get("outputs", []):
        if o.get("name") == "stderr": continue
        t = "".join(o.get("text", "")) or "".join(o.get("data", {}).get("text/plain", "")) or "".join(o.get("traceback", []))[-1500:]
        print(t[:3000])

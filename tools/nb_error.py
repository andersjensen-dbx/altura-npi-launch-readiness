import json, re, sys
nb = json.load(open(sys.argv[1]))
for i, c in enumerate(nb["cells"]):
    for o in c.get("outputs", []):
        if o.get("output_type") == "error":
            print(f"cell {i}: {o['ename']}: {re.sub(r'\x1b\[[0-9;]*m', '', o['evalue'])[:1500]}")
            print("".join(c["source"])[:600])

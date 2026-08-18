import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/notebook-manager/primitive_traces.jsonl"
os.makedirs("p2s_traces/notebook-manager", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_notebook_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PATCH": res = requests.patch(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/5] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/5] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        # Check if Tomcat is up by hitting the root or notebooks endpoint
        r = requests.get(f"{PROXY_URL}/api/notebooks", params={"page":0, "pageSize":1}, timeout=1)
        if r.status_code in [200, 400, 404]: 
            print("  [HEALTHCHECK] Notebook Manager API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 5 Operations for Notebook Manager ===")

# 1. Get Paginated List (Pre-seeded DB has 6 items)
record("GET", "/api/notebooks", params={"page": 0, "pageSize": 10}, flow_id="flow_inventory")

# 2. Create a new notebook
nb_resp = record("POST", "/api/notebooks", json_body={"name": "Lenovo ThinkPad P1", "currentPrice": 1299.99}, flow_id="flow_inventory")
nb_id = nb_resp.get("id", 7) if isinstance(nb_resp, dict) else 7

# 3. Retrieve the newly created notebook
record("GET", f"/api/notebooks/{nb_id}", flow_id="flow_inventory")

# 4. Patch/Update the notebook
record("PATCH", f"/api/notebooks/{nb_id}", json_body={"name": "Lenovo ThinkPad P1 Gen 5", "currentPrice": 1499.99}, flow_id="flow_inventory")

# 5. Delete the notebook
record("DELETE", f"/api/notebooks/{nb_id}", flow_id="flow_inventory")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

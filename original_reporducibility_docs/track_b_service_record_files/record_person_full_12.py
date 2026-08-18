import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/person-controller/primitive_traces.jsonl"
os.makedirs("p2s_traces/person-controller", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_person_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, params=params, timeout=10)

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
        print(f"  [{step_cnt:>2}/12] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/12] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/api/persons/count", timeout=1)
        if r.status_code in [200, 401, 403, 404]: 
            print("  [HEALTHCHECK] Person Controller API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 12 Operations for Person Controller ===")

# Valid Person Payload
person_payload = {
    "firstName": "John",
    "lastName": "Doe",
    "age": 30,
    "insurance": True,
    "address": {
        "street": "Main St",
        "number": 123,
        "city": "New York",
        "country": "United States",
        "postcode": "10001"
    },
    "cars": [
        {"brand": "Tesla", "model": "Model 3", "maxSpeedKmH": 220.0}
    ]
}

# ── FLOW 1: Single Person Operations (4 ops) ──
p1 = record("POST", "/api/person", json_body=person_payload, flow_id="flow_single")
# Extract Mongo ID if it's a string, or use dummy if Spring returns the raw ObjectId struct
p_id = "60f1b2b3b3b3b3b3b3b3b3b3"
if isinstance(p1, dict):
    if isinstance(p1.get("id"), str): p_id = p1["id"]
    elif isinstance(p1.get("id"), dict) and "timestamp" in p1["id"]: p_id = str(p1["id"]["timestamp"])

record("GET", f"/api/person/{p_id}", flow_id="flow_single")
person_payload["firstName"] = "John Updated"
record("PUT", "/api/person", json_body=person_payload, flow_id="flow_single")
record("DELETE", f"/api/person/{p_id}", flow_id="flow_single")

# ── FLOW 2: Bulk Operations (4 ops) ──
record("POST", "/api/persons", json_body=[person_payload, person_payload], flow_id="flow_bulk")
record("GET", "/api/persons", flow_id="flow_bulk")
record("PUT", "/api/persons", json_body=[person_payload], flow_id="flow_bulk")
record("DELETE", "/api/persons", flow_id="flow_bulk")

# ── FLOW 3: Aggregate & Multi-ID Operations (4 ops) ──
# Re-seed a couple for aggregation
record("POST", "/api/persons", json_body=[person_payload, person_payload], flow_id="flow_aggregate")

record("GET", "/api/persons/count", flow_id="flow_aggregate")
record("GET", "/api/persons/averageAge", flow_id="flow_aggregate")

# Test comma-separated ID endpoints
multi_ids = f"{p_id},{p_id}"
record("GET", f"/api/persons/{multi_ids}", flow_id="flow_aggregate")
record("DELETE", f"/api/persons/{multi_ids}", flow_id="flow_aggregate")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

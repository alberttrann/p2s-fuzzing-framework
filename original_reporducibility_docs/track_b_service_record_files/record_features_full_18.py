import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/features-service/primitive_traces.jsonl"
os.makedirs("p2s_traces/features-service", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, form_data=None, flow_id="flow_features_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {}

    try:
        if method == "GET":
            res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            if form_data:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                res = requests.post(url, headers=headers, data=form_data, timeout=10)
            else:
                headers["Content-Type"] = "application/json"
                res = requests.post(url, headers=headers, json=json_body, timeout=10)
        elif method == "PUT":
            if form_data:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                res = requests.put(url, headers=headers, data=form_data, timeout=10)
            else:
                headers["Content-Type"] = "application/json"
                res = requests.put(url, headers=headers, json=json_body, timeout=10)
        elif method == "DELETE":
            res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": path, "headers": headers, "body": json_body or form_data},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/18] {method:6} {path:<45} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/18] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting H2 Database & Waiting 10s for Tomcat ===")
os.system("docker restart restgym_features_service")
time.sleep(10)

print("\n=== 2. Recording ALL 18 Operations for Features Service ===")

# 1. Product Lifecycle (3 ops)
record("GET", "/products", flow_id="flow_features")
record("POST", "/products/SMARTPHONE", flow_id="flow_features")
record("GET", "/products/SMARTPHONE", flow_id="flow_features")

# 2. Features Lifecycle (3 ops)
record("GET", "/products/SMARTPHONE/features", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/features/CAMERA", form_data={"description": "High-Res Camera"}, flow_id="flow_features")
record("PUT", "/products/SMARTPHONE/features/CAMERA", form_data={"description": "4K Ultra-HD Camera"}, flow_id="flow_features")

# 3. Constraints (3 ops)
record("POST", "/products/SMARTPHONE/constraints/requires", form_data={"sourceFeature": "CAMERA", "requiredFeature": "STORAGE"}, flow_id="flow_features")
record("POST", "/products/SMARTPHONE/constraints/excludes", form_data={"sourceFeature": "CAMERA", "excludedFeature": "FM_RADIO"}, flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/constraints/1", flow_id="flow_features")

# 4. Configurations (7 ops)
record("GET", "/products/SMARTPHONE/configurations", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")
record("GET", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/configurations/PRO_CONFIG/features/CAMERA", flow_id="flow_features")
record("GET", "/products/SMARTPHONE/configurations/PRO_CONFIG/features", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/configurations/PRO_CONFIG/features/CAMERA", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")

# Cleanups (2 ops)
record("DELETE", "/products/SMARTPHONE/features/CAMERA", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE", flow_id="flow_features")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

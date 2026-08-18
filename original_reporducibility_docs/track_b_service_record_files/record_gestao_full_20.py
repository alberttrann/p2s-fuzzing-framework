import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/gestao-hospital/primitive_traces.jsonl"
os.makedirs("p2s_traces/gestao-hospital", exist_ok=True)

# Pre-seeded MongoDB ObjectIds from init-mongo.js
HOSPITAL_CENTRAL = "507f1f77bcf86cd799439011"
HOSPITAL_SUL = "507f191e810c19729de860ea"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_gestao_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
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
        print(f"  [{step_cnt:>2}/20] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/20] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"http://localhost:8080/v1/hospitais/", timeout=1)
        if r.status_code in [200, 401, 403]:  # Any response means Tomcat is up
            print("  [HEALTHCHECK] Gestao Hospitalar API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 20 Operations for Gestao Hospitalar ===")

# ── FLOW 1: Hospitals & Geospatial (8 ops) ──
record("GET", "/v1/hospitais/", flow_id="flow_hospitals")
h1 = record("POST", "/v1/hospitais/", json_body={"name": "Hospital Norte", "address": "Av Norte 500", "latitude": "-23.50", "longitude": "-46.60", "beds": 100, "availableBeds": 25}, flow_id="flow_hospitals")
h_id = h1.get("id") if isinstance(h1, dict) else HOSPITAL_CENTRAL

record("GET", f"/v1/hospitais/{h_id}", flow_id="flow_hospitals")
record("PUT", f"/v1/hospitais/{h_id}", json_body={"name": "Hospital Norte Atualizado", "address": "Av Norte 500", "latitude": "-23.50", "longitude": "-46.60", "beds": 120, "availableBeds": 30}, flow_id="flow_hospitals")
record("GET", f"/v1/hospitais/{h_id}/leitos", flow_id="flow_hospitals")
record("GET", "/v1/hospitais/maisProximo", params={"lat": -23.5505, "lon": -46.6333, "raioMaximo": 10.0}, flow_id="flow_hospitals")
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/hospitaisProximos", params={"raio": 15.0}, flow_id="flow_hospitals")
record("DELETE", f"/v1/hospitais/{h_id}", flow_id="flow_hospitals")

# ── FLOW 2: Medical Stock & Transfers (6 ops) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque", flow_id="flow_stock")
p1 = record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque", json_body={"name": "Soro Fisiologico", "productName": "Soro", "productType": "COMMON", "quantity": 100, "description": "Solucao 500ml"}, flow_id="flow_stock")
p_id = p1.get("id") if isinstance(p1, dict) else "673e1f77bcf86cd799439099"

record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", flow_id="flow_stock")
record("PUT", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", json_body={"name": "Soro Fisiologico", "productName": "Soro", "productType": "COMMON", "quantity": 150, "description": "Solucao 500ml"}, flow_id="flow_stock")
record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/transferencia/{p_id}", json_body=50, flow_id="flow_stock") # Sends an int body
record("DELETE", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", flow_id="flow_stock")

# ── FLOW 3: Patients Check-In/Check-Out (5 ops) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes", flow_id="flow_patients")
pat1 = record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/checkin", json_body={"name": "Carlos Eduardo", "cpf": "12345678901", "gender": "MASCULINO", "active": True}, flow_id="flow_patients")
pat_id = pat1.get("id") if isinstance(pat1, dict) else "673e1f77bcf86cd799439111"

record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/{pat_id}", flow_id="flow_patients")
record("PUT", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/{pat_id}", json_body={"name": "Carlos Eduardo Atualizado", "cpf": "12345678901", "gender": "MASCULINO", "active": True}, flow_id="flow_patients")
record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/checkout", json_body=pat_id, flow_id="flow_patients") # Sends string body

# ── FLOW 4: Nearby Locations (1 op) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/proximidades", flow_id="flow_locations")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

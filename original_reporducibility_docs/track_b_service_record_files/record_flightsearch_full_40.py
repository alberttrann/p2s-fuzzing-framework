import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/flight-search/primitive_traces.jsonl"
os.makedirs("p2s_traces/flight-search", exist_ok=True)

# Pre-seeded MongoDB UUIDs from init-mongo.js
ISTANBUL_AIRPORT = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
ANKARA_AIRPORT = "c3d4e5f6-a7b8-6c7d-0e1f-2a3b4c5d6e7f"
FLIGHT_IST_ANK = "f1a2b3c4-d5e6-4f5a-6b7c-8d9e0f1a2b3c"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_flightsearch_full"):
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
        print(f"  [{step_cnt:>2}/40] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/40] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/actuator/health", timeout=1)
        if r.status_code == 200:
            print("  [HEALTHCHECK] Flight Search API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 40 Operations for Flight Search API ===")

# ── FLOW 1: Auth & User Management (9 ops) ──
ts = int(time.time())
record("POST", "/api/v1/authentication/user/register", json_body={"email": f"user{ts}@test.com", "password": "Password123!", "firstName": "Test", "lastName": "User", "phoneNumber": "12345678901", "userType": "USER"}, flow_id="flow_users")
record("POST", "/api/v1/authentication/user/login", json_body={"email": f"user{ts}@test.com", "password": "Password123!"}, flow_id="flow_users")
record("POST", "/api/v1/authentication/refresh-token", json_body={"refreshToken": "dummy_refresh_token"}, flow_id="flow_users")
record("GET", "/api/v1/users/me", flow_id="flow_users")
record("PUT", "/api/v1/users/me", json_body={"firstName": "UpdatedTest", "lastName": "User", "phoneNumber": "12345678901"}, flow_id="flow_users")
record("GET", "/api/v1/users", flow_id="flow_users")
record("GET", "/api/v1/users/1", flow_id="flow_users")
record("GET", "/api/v1/tokens", flow_id="flow_users")
record("DELETE", "/api/v1/tokens/1", flow_id="flow_users")

# ── FLOW 2: Airports Management (8 ops) ──
record("GET", "/api/v1/airports", flow_id="flow_airports")
apt1 = record("POST", "/api/v1/airports", json_body={"name": "Bodrum Milas Airport", "cityName": "Bodrum"}, flow_id="flow_airports")
apt_id1 = apt1.get("response", {}).get("id") if isinstance(apt1, dict) and isinstance(apt1.get("response"), dict) else ISTANBUL_AIRPORT

record("GET", f"/api/v1/airports/{ISTANBUL_AIRPORT}", flow_id="flow_airports")
record("GET", "/api/v1/airports/search", params={"query": "Istanbul"}, flow_id="flow_airports")
record("GET", "/api/v1/airports/city/Istanbul", flow_id="flow_airports")
record("PUT", f"/api/v1/airports/{ISTANBUL_AIRPORT}", json_body={"name": "Istanbul Int Airport", "cityName": "Istanbul"}, flow_id="flow_airports")
record("POST", "/api/v1/airports/batch", json_body=[{"name": "Izmir Airport", "cityName": "Izmir"}], flow_id="flow_airports")
record("DELETE", f"/api/v1/airports/{apt_id1}", flow_id="flow_airports")

# ── FLOW 3: Flights Management & Search (15 ops) ──
record("GET", "/api/v1/flights", flow_id="flow_flights")
flt = record("POST", "/api/v1/flights", json_body={
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 199.99,
    "departureTime": "2026-09-01T10:00:00Z",
    "arrivalTime": "2026-09-01T11:30:00Z"
}, flow_id="flow_flights")
flt_id = flt.get("response", {}).get("id") if isinstance(flt, dict) and isinstance(flt.get("response"), dict) else FLIGHT_IST_ANK

record("GET", f"/api/v1/flights/{FLIGHT_IST_ANK}", flow_id="flow_flights")
record("GET", f"/api/v1/flights/origin/{ISTANBUL_AIRPORT}", flow_id="flow_flights")
record("GET", f"/api/v1/flights/destination/{ANKARA_AIRPORT}", flow_id="flow_flights")
record("GET", "/api/v1/flights/search", params={"fromAirportId": ISTANBUL_AIRPORT, "toAirportId": ANKARA_AIRPORT, "departureTime": "2026-09-01"}, flow_id="flow_flights")
record("GET", "/api/v1/flights/search/cheapest", flow_id="flow_flights")
record("GET", "/api/v1/flights/search/direct", flow_id="flow_flights")

record("PUT", f"/api/v1/flights/{FLIGHT_IST_ANK}", json_body={
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 249.99,
    "departureTime": "2026-09-01T10:00:00Z",
    "arrivalTime": "2026-09-01T11:30:00Z"
}, flow_id="flow_flights")

record("POST", "/api/v1/flights/batch", json_body=[{
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 150.00,
    "departureTime": "2026-09-02T10:00:00Z",
    "arrivalTime": "2026-09-02T11:30:00Z"
}], flow_id="flow_flights")

record("GET", "/api/v1/flights/price-range", params={"min": 100, "max": 500}, flow_id="flow_flights")
record("GET", "/api/v1/flights/airline/THY", flow_id="flow_flights")
record("GET", "/api/v1/flights/date-range", params={"start": "2026-09-01", "end": "2026-09-30"}, flow_id="flow_flights")
record("PUT", f"/api/v1/flights/{FLIGHT_IST_ANK}/price", params={"price": 299.99}, flow_id="flow_flights")
record("DELETE", f"/api/v1/flights/{flt_id}", flow_id="flow_flights")

# ── FLOW 4: System & Actuator (8 ops) ──
record("GET", "/actuator/health", flow_id="flow_system")
record("GET", "/actuator/info", flow_id="flow_system")
record("GET", "/actuator/metrics", flow_id="flow_system")
record("GET", "/actuator/env", flow_id="flow_system")
record("GET", "/actuator/loggers", flow_id="flow_system")
record("GET", "/v3/api-docs", flow_id="flow_system")
record("GET", "/swagger-ui/index.html", flow_id="flow_system")
record("DELETE", "/api/v1/users/me", flow_id="flow_cleanup")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations across 4 execution flows directly to {OUT_FILE}!")

import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/market/primitive_traces.jsonl"
os.makedirs("p2s_traces/market", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_market_full"):
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
        print(f"  [{step_cnt:>2}/13] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/13] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/products", timeout=1)
        if r.status_code in [200, 401, 403]:  # Any response means Tomcat is up
            print("  [HEALTHCHECK] Market API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 13 Operations for Market API ===")

# ── FLOW 1: Auth & User Profile (3 ops) ──
ts = int(time.time())
record("POST", "/register", json_body={"email": f"new_customer_{ts}@test.com", "password": "Password123!", "name": "New Customer", "address": "123 Main St", "phone": "+1234567890"}, flow_id="flow_profile")
record("GET", "/customer", flow_id="flow_profile")
record("GET", "/customer/contacts", flow_id="flow_profile")
record("PUT", "/customer/contacts", json_body={"address": "456 Updated Ave", "phone": "+1987654321"}, flow_id="flow_profile")

# ── FLOW 2: Product Browsing (2 ops) ──
record("GET", "/products", flow_id="flow_shopping")
# Pre-seeded product ID 2 is "Uigeadail" from data.sql
record("GET", "/products/2", flow_id="flow_shopping")

# ── FLOW 3: Shopping Cart & Checkout Lifecycle (5 ops) ──
record("GET", "/customer/cart", flow_id="flow_shopping")
# Add product ID 2 to cart
record("PUT", "/customer/cart", json_body={"productId": 2, "quantity": 1}, flow_id="flow_shopping")
# Include delivery
record("PUT", "/customer/cart/delivery", params={"included": "true"}, flow_id="flow_shopping")
# Pay and Checkout
order_resp = record("POST", "/customer/cart/pay", json_body={"ccNumber": "1111222233334444"}, flow_id="flow_shopping")
order_id = order_resp.get("id", 1) if isinstance(order_resp, dict) else 1

# ── FLOW 4: Order History & Cleanup (3 ops) ──
record("GET", "/customer/orders", flow_id="flow_orders")
record("GET", f"/customer/orders/{order_id}", flow_id="flow_orders")
record("DELETE", "/customer/cart", flow_id="flow_orders")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

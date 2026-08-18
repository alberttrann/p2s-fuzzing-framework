import json
import os
import requests

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/erc20/primitive_traces.jsonl"
os.makedirs("p2s_traces/erc20", exist_ok=True)

DUMMY_ADDR = "0x0000000000000000000000000000000000000000"
OWNER_ADDR = "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1"
SPENDER_ADDR = "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_erc20_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)

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
        print(f"  [{step_cnt:>2}/13] {method:6} {full_path_str[:50]:<50} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/13] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Deploying Fresh ERC-20 Contract ===")
os.system("docker exec restgym_erc20 python3 /api/init-contract.py")

print("\n=== 2. Recording ALL 13 Operations for ERC-20 Token Lifecycle ===")

# 1. Config & Metadata (6 ops)
record("GET", "/config", flow_id="flow_erc20")
record("POST", "/deploy", json_body={"initialAmount": 1000000, "tokenName": "TestToken", "decimalUnits": 18, "tokenSymbol": "TST"}, flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/name", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/symbol", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/decimals", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/totalSupply", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/version", flow_id="flow_erc20")

# 2. Balance & Approvals (3 ops)
record("GET", f"/{DUMMY_ADDR}/balanceOf/{OWNER_ADDR}", flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/approve", json_body={"spender": SPENDER_ADDR, "value": 1000}, flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/allowance", params={"ownerAddress": OWNER_ADDR, "spenderAddress": SPENDER_ADDR}, flow_id="flow_erc20")

# 3. ApproveAndCall, Transfer & TransferFrom (3 ops)
record("POST", f"/{DUMMY_ADDR}/approveAndCall", json_body={"spender": SPENDER_ADDR, "value": 500, "extraData": "0x00"}, flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/transfer", json_body={"to": SPENDER_ADDR, "value": 250}, flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/transferFrom", json_body={"from": OWNER_ADDR, "to": SPENDER_ADDR, "value": 100}, flow_id="flow_erc20")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

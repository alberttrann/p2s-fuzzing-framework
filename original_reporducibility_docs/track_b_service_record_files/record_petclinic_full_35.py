import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090/petclinic"
OUT_FILE = "p2s_traces/pet-clinic/primitive_traces.jsonl"
os.makedirs("p2s_traces/pet-clinic", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_petclinic_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    
    # Inject Basic Auth (admin:admin) so requests succeed
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic YWRtaW46YWRtaW4="
    }

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
        print(f"  [{step_cnt:>2}/35] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/35] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting Database ===")
os.system("docker restart restgym_petclinic")
time.sleep(12)

print("\n=== 2. Recording ALL Operations for PetClinic API ===")

# ── FLOW 1: Vets & Specialties (9 ops) ──
record("GET", "/api/specialties", flow_id="flow_clinic")
spec = record("POST", "/api/specialties", json_body={"name": "Cardiology"}, flow_id="flow_clinic")
sid = spec.get("id", 4) if isinstance(spec, dict) else 4
record("GET", f"/api/specialties/{sid}", flow_id="flow_clinic")
record("PUT", f"/api/specialties/{sid}", json_body={"name": "Advanced Cardiology"}, flow_id="flow_clinic")

record("GET", "/api/vets", flow_id="flow_clinic")
vet = record("POST", "/api/vets", json_body={"firstName": "John", "lastName": "Smith", "specialties": [{"id": sid, "name": "Advanced Cardiology"}]}, flow_id="flow_clinic")
vid = vet.get("id", 7) if isinstance(vet, dict) else 7
record("GET", f"/api/vets/{vid}", flow_id="flow_clinic")
record("PUT", f"/api/vets/{vid}", json_body={"firstName": "John", "lastName": "Smith-Doe", "specialties": [{"id": sid, "name": "Advanced Cardiology"}]}, flow_id="flow_clinic")
record("DELETE", f"/api/vets/{vid}", flow_id="flow_clinic")
record("DELETE", f"/api/specialties/{sid}", flow_id="flow_clinic")

# ── FLOW 2: Pet Types (5 ops) ──
record("GET", "/api/pettypes", flow_id="flow_pets")
ptype = record("POST", "/api/pettypes", json_body={"name": "Parrot"}, flow_id="flow_pets")
ptid = ptype.get("id", 7) if isinstance(ptype, dict) else 7
record("GET", f"/api/pettypes/{ptid}", flow_id="flow_pets")
record("PUT", f"/api/pettypes/{ptid}", json_body={"name": "Macaw"}, flow_id="flow_pets")
record("DELETE", f"/api/pettypes/{ptid}", flow_id="flow_pets")

# ── FLOW 3: Owners, Pets, and Visits (15 ops) ──
record("GET", "/api/owners", flow_id="flow_owners")
record("GET", "/api/owners/*/lastname/Davis", flow_id="flow_owners")
owner = record("POST", "/api/owners", json_body={"firstName": "Alice", "lastName": "Wonderland", "address": "123 Rabbit Hole", "city": "London", "telephone": "1234567890"}, flow_id="flow_owners")
oid = owner.get("id", 11) if isinstance(owner, dict) else 11
record("GET", f"/api/owners/{oid}", flow_id="flow_owners")
record("PUT", f"/api/owners/{oid}", json_body={"firstName": "Alice", "lastName": "Wonderland", "address": "456 Queen St", "city": "London", "telephone": "1234567890"}, flow_id="flow_owners")

record("GET", "/api/pets", flow_id="flow_owners")
pet = record("POST", "/api/pets", json_body={"name": "Cheshire", "birthDate": "2020-01-01", "type": {"id": 1, "name": "cat"}, "ownerId": oid}, flow_id="flow_owners")
pid = pet.get("id", 14) if isinstance(pet, dict) else 14
record("GET", f"/api/pets/{pid}", flow_id="flow_owners")
record("PUT", f"/api/pets/{pid}", json_body={"name": "Cheshire Cat", "birthDate": "2020-01-01", "type": {"id": 1, "name": "cat"}, "ownerId": oid}, flow_id="flow_owners")

record("GET", "/api/visits", flow_id="flow_owners")
visit = record("POST", "/api/visits", json_body={"date": "2026-10-10", "description": "Annual checkup", "petId": pid}, flow_id="flow_owners")
vid = visit.get("id", 5) if isinstance(visit, dict) else 5
record("GET", f"/api/visits/{vid}", flow_id="flow_owners")
record("PUT", f"/api/visits/{vid}", json_body={"date": "2026-10-11", "description": "Rescheduled checkup", "petId": pid}, flow_id="flow_owners")

record("DELETE", f"/api/visits/{vid}", flow_id="flow_owners")
record("DELETE", f"/api/pets/{pid}", flow_id="flow_owners")
record("DELETE", f"/api/owners/{oid}", flow_id="flow_owners")

# ── FLOW 4: Users (2 ops) ──
record("POST", "/api/users", json_body={"username": "newvet", "password": "password123", "enabled": True, "roles": [{"name": "ROLE_VET"}]}, flow_id="flow_users")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL operations directly to {OUT_FILE}!")

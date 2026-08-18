import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/project-tracking-system/primitive_traces.jsonl"
os.makedirs("p2s_traces/project-tracking-system", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_pts_full"):
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
        print(f"  [{step_cnt:>2}/59] {method:6} {full_path_str[:60]:<60} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/59] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/app/api/locations", timeout=1)
        if r.status_code in [200, 401, 403]: 
            print("  [HEALTHCHECK] Project Tracking System API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 59 Operations ===")

# Base Objects for creation
loc_body = {"adr": "123 P2S Ave", "postalCode": "10001", "city": "Fuzz City"}
dept_body = {"departmentName": "Security QA", "location": {"locationId": 1}}
emp_body = {"firstName": "Test", "lastName": "User", "email": "test@test.com", "phone": "123", "job": "Tester", "salary": 5000.0, "department": {"departmentId": 4}}
proj_body = {"title": "P2S Evaluation", "startDate": "2026-08-01", "endDate": "2026-12-31", "status": "IN_PROGRESS"}
cred_body = {"username": "fuzzer", "password": "pwd", "enabled": True, "role": "ROLE_EMP"}

# ── 1. Locations (9 ops) ──
record("GET", "/app/api/locations", flow_id="flow_locations")
loc = record("POST", "/app/api/locations/save", json_body=loc_body, flow_id="flow_locations")
lid = loc.get("locationId", 3) if isinstance(loc, dict) else 3
record("GET", f"/app/api/locations/{lid}", flow_id="flow_locations")
record("PUT", "/app/api/locations/update", json_body={"locationId": lid, "city": "Updated City"}, flow_id="flow_locations")
record("POST", "/app/api/locations", json_body=loc_body, flow_id="flow_locations")
record("PUT", "/app/api/locations", json_body={"locationId": lid, "city": "Updated 2"}, flow_id="flow_locations")
record("DELETE", "/app/api/locations/delete", params={"locationId": lid}, flow_id="flow_locations")
loc2 = record("POST", "/app/api/locations", json_body=loc_body, flow_id="flow_locations")
lid2 = loc2.get("locationId", 4) if isinstance(loc2, dict) else 4
record("DELETE", f"/app/api/locations/{lid2}", flow_id="flow_locations")

# ── 2. Departments (9 ops) ──
record("GET", "/app/api/departments", flow_id="flow_depts")
dept = record("POST", "/app/api/departments/save", json_body=dept_body, flow_id="flow_depts")
did = dept.get("departmentId", 7) if isinstance(dept, dict) else 7
record("GET", f"/app/api/departments/{did}", flow_id="flow_depts")
record("PUT", "/app/api/departments/update", json_body={"departmentId": did, "departmentName": "Updated Dept"}, flow_id="flow_depts")
record("POST", "/app/api/departments", json_body=dept_body, flow_id="flow_depts")
record("PUT", "/app/api/departments", json_body={"departmentId": did, "departmentName": "Updated 2"}, flow_id="flow_depts")
record("DELETE", "/app/api/departments/delete", params={"departmentId": did}, flow_id="flow_depts")
dept2 = record("POST", "/app/api/departments", json_body=dept_body, flow_id="flow_depts")
did2 = dept2.get("departmentId", 8) if isinstance(dept2, dict) else 8
record("DELETE", f"/app/api/departments/{did2}", flow_id="flow_depts")

# ── 3. Projects (10 ops) ──
record("GET", "/app/api/projects", flow_id="flow_projects")
proj = record("POST", "/app/api/projects/save", json_body=proj_body, flow_id="flow_projects")
pid = proj.get("projectId", 10) if isinstance(proj, dict) else 10
record("GET", f"/app/api/projects/{pid}", flow_id="flow_projects")
record("PUT", "/app/api/projects/update", json_body={"projectId": pid, "title": "Updated Proj"}, flow_id="flow_projects")
record("POST", "/app/api/projects", json_body=proj_body, flow_id="flow_projects")
record("PUT", "/app/api/projects", json_body={"projectId": pid, "title": "Updated 2"}, flow_id="flow_projects")
record("DELETE", "/app/api/projects/delete", params={"projectId": pid}, flow_id="flow_projects")
proj2 = record("POST", "/app/api/projects", json_body=proj_body, flow_id="flow_projects")
pid2 = proj2.get("projectId", 11) if isinstance(proj2, dict) else 11
record("DELETE", f"/app/api/projects/{pid2}", flow_id="flow_projects")
record("DELETE", "/app/api/projects/delete", flow_id="flow_projects") # Trigger 400 with missing param

# ── 4. Employees (13 ops) ──
record("GET", "/app/api/employees", flow_id="flow_employees")
emp = record("POST", "/app/api/employees/save", json_body=emp_body, flow_id="flow_employees")
eid = emp.get("employeeId", 15) if isinstance(emp, dict) else 15
record("GET", f"/app/api/employees/{eid}", flow_id="flow_employees")
record("GET", "/app/api/employees/data/department/4", flow_id="flow_employees")
record("GET", "/app/api/employees/data/employee-project-data/1", flow_id="flow_employees")
record("GET", "/app/api/employees/data/manager-project-data/4", flow_id="flow_employees")
record("PUT", "/app/api/employees/update", json_body={"employeeId": eid, "firstName": "Updated"}, flow_id="flow_employees")
record("POST", "/app/api/employees", json_body=emp_body, flow_id="flow_employees")
record("PUT", "/app/api/employees", json_body={"employeeId": eid, "firstName": "Updated 2"}, flow_id="flow_employees")
record("DELETE", "/app/api/employees/delete", params={"employeeId": eid}, flow_id="flow_employees")
emp2 = record("POST", "/app/api/employees", json_body=emp_body, flow_id="flow_employees")
eid2 = emp2.get("employeeId", 16) if isinstance(emp2, dict) else 16
record("DELETE", f"/app/api/employees/username/admin", flow_id="flow_employees")
record("GET", "/app/api/employees/username/admin", flow_id="flow_employees")

# ── 5. Credentials (9 ops) ──
record("GET", "/app/api/credentials", flow_id="flow_credentials")
cred = record("POST", "/app/api/credentials/save", json_body=cred_body, flow_id="flow_credentials")
crid = cred.get("credentialId", 15) if isinstance(cred, dict) else 15
record("GET", f"/app/api/credentials/{crid}", flow_id="flow_credentials")
record("GET", "/app/api/credentials/username/fuzzer", flow_id="flow_credentials")
record("PUT", "/app/api/credentials/update", json_body={"credentialId": crid, "username": "fuzzer_updated"}, flow_id="flow_credentials")
record("POST", "/app/api/credentials", json_body=cred_body, flow_id="flow_credentials")
record("PUT", "/app/api/credentials", json_body={"credentialId": crid, "username": "updated2"}, flow_id="flow_credentials")
record("DELETE", "/app/api/credentials/delete", params={"credentialId": crid}, flow_id="flow_credentials")
record("DELETE", "/app/api/credentials/username/fuzzer_updated", flow_id="flow_credentials")

# ── 6. Assignments & Commits (9 ops) ──
# We use existing DB seeds: Employee 1, Project 1
commit_date = "2020-11-26T10:50:09"
assign_body = {"employeeId": 1, "projectId": 2, "commitEmpDesc": "Test commit", "commitMgrDesc": "Approved"}

record("GET", "/app/api/assignments", flow_id="flow_assignments")
record("GET", "/app/api/assignments/1/1", flow_id="flow_assignments")
record("GET", f"/app/api/assignments/1/1/{commit_date}", flow_id="flow_assignments")
record("GET", "/app/api/assignments/data/project-commit/1", flow_id="flow_assignments")
record("GET", "/app/api/assignments/data/project-commit/1/1", flow_id="flow_assignments")
record("POST", "/app/api/assignments/save", json_body=assign_body, flow_id="flow_assignments")
record("POST", "/app/api/assignments", json_body=assign_body, flow_id="flow_assignments")
record("PUT", "/app/api/assignments/update", json_body=assign_body, flow_id="flow_assignments")
record("PUT", "/app/api/assignments", json_body=assign_body, flow_id="flow_assignments")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

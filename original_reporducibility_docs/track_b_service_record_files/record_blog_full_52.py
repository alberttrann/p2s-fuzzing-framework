import json
import os
import requests

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/blog/primitive_traces.jsonl"
os.makedirs("p2s_traces/blog", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_blog_full"):
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
            "request": {
                "method": method,
                "path": full_path_str,
                "headers": headers,
                "body": json_body
            },
            "response": {
                "status_code": res.status_code,
                "body": res_data
            }
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/52] {method:6} {full_path_str[:50]:<50} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/52] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting MySQL Database inside Container ===")
os.system("docker exec restgym_blog mysql -ublog -pblog blogapi < apis/blog/database/blogapi.sql")

print("\n=== 2. Recording ALL 52 Endpoints Trace Across 4 Flows ===")

# ── FLOW 1: User & Auth Endpoints (12 ops) ──
record("GET", "/api/users/checkUsernameAvailability", params={"username": "userusername"}, flow_id="flow_users")
record("GET", "/api/users/checkEmailAvailability", params={"email": "user@gmail.com"}, flow_id="flow_users")
me = record("GET", "/api/users/me", flow_id="flow_users")
uname = me.get("username", "userusername") if isinstance(me, dict) else "userusername"

record("POST", "/api/users", json_body={"username":"newuser","password":"password123","email":"new@gmail.com","firstName":"New","lastName":"User"}, flow_id="flow_users")
record("PUT", "/api/users/setOrUpdateInfo", json_body={"firstName":"UpdatedFirst","lastName":"UpdatedLast"}, flow_id="flow_users")
record("PUT", f"/api/users/{uname}", json_body={"firstName":"UserFirst","lastName":"UserLast","email":"user@gmail.com"}, flow_id="flow_users")
record("GET", f"/api/users/{uname}/profile", flow_id="flow_users")
record("GET", f"/api/users/{uname}/posts", flow_id="flow_users")
record("GET", f"/api/users/{uname}/albums", flow_id="flow_users")
record("PUT", f"/api/users/{uname}/giveAdmin", flow_id="flow_users")
record("PUT", f"/api/users/{uname}/takeAdmin", flow_id="flow_users")
record("DELETE", f"/api/users/newuser", flow_id="flow_users")

# ── FLOW 2: Categories, Tags, Posts & Comments (22 ops) ──
record("GET", "/api/categories", params={"page":0,"size":10}, flow_id="flow_content")
c1 = record("POST", "/api/categories", json_body={"name":"Technology"}, flow_id="flow_content")
cid = c1.get("id", 1) if isinstance(c1, dict) else 1
record("GET", f"/api/categories/{cid}", flow_id="flow_content")
record("PUT", f"/api/categories/{cid}", json_body={"name":"Tech & AI"}, flow_id="flow_content")

record("GET", "/api/tags", params={"page":0,"size":10}, flow_id="flow_content")
t1 = record("POST", "/api/tags", json_body={"name":"AI"}, flow_id="flow_content")
tid = t1.get("id", 1) if isinstance(t1, dict) else 1
record("GET", f"/api/tags/{tid}", flow_id="flow_content")
record("PUT", f"/api/tags/{tid}", json_body={"name":"Artificial Intelligence"}, flow_id="flow_content")

record("GET", "/api/posts", params={"page":0,"size":10}, flow_id="flow_content")
p1 = record("POST", "/api/posts", json_body={"title":"AI Fuzzing","body":"P2S testing blog api","categoryId":cid,"tags":["AI"]}, flow_id="flow_content")
pid = p1.get("id", 1) if isinstance(p1, dict) else 1
record("GET", f"/api/posts/{pid}", flow_id="flow_content")
record("GET", f"/api/posts/category/{cid}", params={"page":0,"size":10}, flow_id="flow_content")
record("GET", f"/api/posts/tag/{tid}", params={"page":0,"size":10}, flow_id="flow_content")
record("PUT", f"/api/posts/{pid}", json_body={"title":"Updated AI Fuzzing","body":"Updated content","categoryId":cid,"tags":["AI"]}, flow_id="flow_content")

record("GET", f"/api/posts/{pid}/comments", params={"page":0,"size":10}, flow_id="flow_content")
cm1 = record("POST", f"/api/posts/{pid}/comments", json_body={"body":"Great post!"}, flow_id="flow_content")
cmid = cm1.get("id", 1) if isinstance(cm1, dict) else 1
record("GET", f"/api/posts/{pid}/comments/{cmid}", flow_id="flow_content")
record("PUT", f"/api/posts/{pid}/comments/{cmid}", json_body={"body":"Updated comment!"}, flow_id="flow_content")
record("DELETE", f"/api/posts/{pid}/comments/{cmid}", flow_id="flow_content")

record("DELETE", f"/api/categories/{cid}", flow_id="flow_content")
record("DELETE", f"/api/tags/{tid}", flow_id="flow_content")
record("DELETE", f"/api/posts/{pid}", flow_id="flow_content")

# ── FLOW 3: Albums & Photos (11 ops) ──
record("GET", "/api/albums", params={"page":0,"size":10}, flow_id="flow_media")
a1 = record("POST", "/api/albums", json_body={"title":"My Tech Album","photo":"cover.jpg"}, flow_id="flow_media")
aid = a1.get("id", 1) if isinstance(a1, dict) else 1
record("GET", f"/api/albums/{aid}", flow_id="flow_media")
record("PUT", f"/api/albums/{aid}", json_body={"title":"Updated Tech Album","photo":"cover2.jpg"}, flow_id="flow_media")
record("GET", f"/api/albums/{aid}/photos", params={"page":0,"size":10}, flow_id="flow_media")

record("GET", "/api/photos", params={"page":0,"size":10}, flow_id="flow_media")
ph1 = record("POST", "/api/photos", json_body={"albumId":aid,"title":"Diagram","url":"http://img.com/1.png","thumbnailUrl":"http://img.com/1_thumb.png"}, flow_id="flow_media")
phid = ph1.get("id", 1) if isinstance(ph1, dict) else 1
record("GET", f"/api/photos/{phid}", flow_id="flow_media")
record("PUT", f"/api/photos/{phid}", json_body={"albumId":aid,"title":"Updated Diagram","url":"http://img.com/2.png","thumbnailUrl":"http://img.com/2_thumb.png"}, flow_id="flow_media")
record("DELETE", f"/api/photos/{phid}", flow_id="flow_media")
record("DELETE", f"/api/albums/{aid}", flow_id="flow_media")

# ── FLOW 4: Todos (7 ops) ──
record("GET", "/api/todos", params={"page":0,"size":10}, flow_id="flow_todos")
td1 = record("POST", "/api/todos", json_body={"title":"Finish P2S Eval","completed":False}, flow_id="flow_todos")
tdid = td1.get("id", 1) if isinstance(td1, dict) else 1
record("GET", f"/api/todos/{tdid}", flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}", json_body={"title":"Finish P2S Eval Updated","completed":False}, flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}/complete", json_body={}, flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}/unComplete", json_body={}, flow_id="flow_todos")
record("DELETE", f"/api/todos/{tdid}", flow_id="flow_todos")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations across 4 execution flows directly to {OUT_FILE}!")

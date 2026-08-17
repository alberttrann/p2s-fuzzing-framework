import requests, time, psycopg2

def pre_snapshot_hook(active_db_name: str):
    """
    Registers the Coordinator account and forces DB roles to match trace UUIDs
    before P2S freezes the first Postgres template snapshot.
    """
    print(f"[*] SEAL Hook: Registering Coordinator on '{active_db_name}'...")
    try:
        requests.post("http://localhost:8080/api/auth/register", json={
            "email": "coordinator@seal.eval",
            "password": "Eval@1234567",
            "fullName": "P2S Eval Coordinator"
        }, timeout=10)
        time.sleep(1)

        # Exact UUID from the captured traces
        coord_id = "f6aedc49-ab54-4ed2-9668-abc9eb337e34"

        conn = psycopg2.connect(
            f"postgresql://postgres:postgres@localhost:5432/{active_db_name}"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_roles "
                "WHERE user_id=(SELECT id FROM users WHERE email='coordinator@seal.eval');"
            )
            cur.execute(
                f"UPDATE users SET id='{coord_id}', status='approved' "
                f"WHERE email='coordinator@seal.eval';"
            )
            cur.execute(
                f"INSERT INTO user_roles (user_id, role_id) "
                f"SELECT '{coord_id}', id FROM roles "
                f"WHERE name IN ('team_member', 'coordinator') ON CONFLICT DO NOTHING;"
            )
        conn.close()
        print("[+] SEAL Hook complete.")
    except Exception as e:
        print(f"[!] SEAL Hook failed: {e}")

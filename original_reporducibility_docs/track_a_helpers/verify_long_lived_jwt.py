#!/usr/bin/env python3
"""Verify that the currently running local Track-A backend issues a long-lived JWT."""
import os, json, urllib.request, base64, datetime
base=os.environ.get('SEAL_BASE_URL','http://localhost:8080/api').rstrip('/')
email=os.environ.get('SEAL_COORD_EMAIL','coordinator@seal.eval')
password=os.environ.get('SEAL_COORD_PASSWORD','Eval@1234567')
req=urllib.request.Request(base+'/auth/login',data=json.dumps({'email':email,'password':password}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as resp:
    token=json.loads(resp.read().decode()).get('accessToken','')
if not token: raise SystemExit('No accessToken returned')
seg=token.split('.')[1]
seg += '='*((4-len(seg)%4)%4)
payload=json.loads(base64.urlsafe_b64decode(seg).decode())
exp=datetime.datetime.fromtimestamp(payload['exp'],tz=datetime.timezone.utc)
iat=datetime.datetime.fromtimestamp(payload.get('iat',0),tz=datetime.timezone.utc)
now=datetime.datetime.now(datetime.timezone.utc)
days=(exp-now).days
print('Token Issued At :',iat)
print('Token Expires At:',exp)
print('Token Lifespan  :',days,'days')
if days <= 30: raise SystemExit('[FAIL] Backend still appears to issue a short-lived token')
print('[OK] Long-lived token confirmed')

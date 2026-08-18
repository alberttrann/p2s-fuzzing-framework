#!/usr/bin/env python3
"""Sanitize the Track-A OpenAPI contract exactly for baseline stability.

- force server URL to http://localhost:8080/api
- remove /auth/logout
- remove DELETE /users/{id}
- remove DELETE /users/me
"""
import argparse, json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('spec', nargs='?', default='seal_openapi.json')
a=p.parse_args()
path=Path(a.spec)
spec=json.loads(path.read_text(encoding='utf-8'))
spec['servers']=[{'url':'http://localhost:8080/api'}]
paths=spec.get('paths',{})
paths.pop('/auth/logout',None)
if '/users/{id}' in paths: paths['/users/{id}'].pop('delete',None)
if '/users/me' in paths: paths['/users/me'].pop('delete',None)
path.write_text(json.dumps(spec,indent=2),encoding='utf-8')
print(f'[OK] sanitized {path}')

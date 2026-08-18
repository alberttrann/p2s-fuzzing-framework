#!/usr/bin/env python3
"""Track-A AutoRestTest post-hoc artifact audit.

This reproduces the defensible checks retained from the experiment notes:
1) count persisted server_errors.json records;
2) list records by operation;
3) count null/empty vs non-empty parameter maps.

The older keyword classifier that assigned every unmatched record to a
"Deep Business Logic Error" residual category is intentionally not used as a
security conclusion. Preserve it only as historical exploratory analysis.
"""
import argparse, json
from pathlib import Path
from collections import Counter
p=argparse.ArgumentParser()
p.add_argument('--server-errors',default='data/seal_openapi/server_errors.json')
a=p.parse_args()
path=Path(a.server_errors)
data=json.loads(path.read_text(encoding='utf-8'))
counts=Counter({op:len(errs) for op,errs in data.items()})
total=empty=nonempty=0
for op,errs in data.items():
    for err in errs:
        total+=1
        params=err.get('parameters')
        if params is None or params=={} or params==[]: empty+=1
        else: nonempty+=1
print('='*72)
print('AUTORESTTEST PERSISTED SERVER-ERROR ARTIFACT AUDIT')
print('='*72)
print('File:',path)
print('Persisted records:',total)
print('Null/empty parameters:',empty, f'({100*empty/max(1,total):.2f}%)')
print('Non-empty parameters :',nonempty, f'({100*nonempty/max(1,total):.2f}%)')
print('\nRecords by operation:')
for op,n in counts.most_common(): print(f'  {op:<45} {n:>6}')
print('\nInterpretation boundary: these are persisted server-error records, not verified vulnerabilities.')

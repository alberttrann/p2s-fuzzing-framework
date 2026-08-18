#!/usr/bin/env python3
# Historical Track-A parser preserved from the experiment note.
# IMPORTANT: HTTP 200 in an IDOR-themed probe is a candidate only; inspect the body/action before any disclosure claim.
# Generic Schemathesis 500 bodies do not reveal the underlying exception class.
import json, os, re
from collections import Counter

print('=' * 80)
print('  DYNAMIC POST-HOC QUALITATIVE FAULT CLASSIFICATION (ALL BASELINES)')
print('=' * 80)

# ==============================================================================
# 1. CATS DYNAMIC PARSER & VERIFIER
# ==============================================================================
cats_dir = 'cats_report'

cats_fuzzers_5xx = Counter()
cats_categories = Counter()

sqli_total = 0
sqli_framework_crashes = 0
sqli_db_syntax_errors = 0
sqli_crash_logs = []  # <--- NEW: Stores the response body samples

idor_total = 0
idor_200_count = 0
idor_failed_exploits = 0
idor_200_logs = []

total_5xx_files = 0

for root, dirs, files in os.walk(cats_dir):
    for file in files:
        if file.lower().startswith('test') and file.endswith('.json'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)
                    
                    response_obj = data.get('response', {}) or {}
                    resp_code = str(response_obj.get('responseCode', ''))
                    json_body = str(response_obj.get('jsonBody', ''))
                    fuzzer = str(data.get('fuzzer', ''))
                    fuzzer_lower = fuzzer.lower()
                    path = str(data.get('path', ''))

                    # A. Track IDORs regardless of 5xx (they look for 2xx)
                    if 'insecuredirectobject' in fuzzer_lower or 'idor' in fuzzer_lower:
                        idor_total += 1
                        if resp_code.startswith('2'):
                            idor_200_count += 1
                            idor_200_logs.append((path, json_body[:60]))
                        else:
                            idor_failed_exploits += 1

                    # B. Track 5xx Errors
                    if resp_code.startswith('5') or resp_code in ['500', '501', '999']:
                        total_5xx_files += 1
                        cats_fuzzers_5xx[fuzzer] += 1
                        
                        # Dynamic Categorization (Substring/Regex)
                        if any(k in fuzzer_lower for k in ['header', 'contenttype', 'accept']):
                            cats_categories['Header & Content-Type Fuzzing'] += 1
                        elif any(k in fuzzer_lower for k in ['char', 'filler', 'string', 'unicode', 'abugida', 'zalgo', 'override']):
                            cats_categories['String, Unicode & Encoding Fuzzing'] += 1
                        elif any(k in fuzzer_lower for k in ['sql', 'xss', 'injection', 'command']):
                            cats_categories['Static Syntax Injections (SQLi/XSS/Command/NoSQL)'] += 1
                        elif any(k in fuzzer_lower for k in ['invalid', 'empty', 'null', 'boundary', 'number', 'integer', 'boolean', 'enum', 'method', 'duplicate', 'mass']):
                            cats_categories['Invalid Reference & Type Boundary Fuzzing'] += 1
                        elif any(k in fuzzer_lower for k in ['idor', 'insecure', 'bypass']):
                            cats_categories['State-Agnostic Auth / IDOR Probing'] += 1
                        elif any(k in fuzzer_lower for k in ['happy', 'new']):
                            cats_categories['Happy Path / Contract Baseline'] += 1
                        else:
                            cats_categories['Unclassified / Other Boundary Fuzzing'] += 1

                        # SQLi Deep Verification
                        if 'sqlinjection' in fuzzer_lower:
                            sqli_total += 1
                            if 'psqlexception' in json_body.lower() or 'sqlgrammarexception' in json_body.lower():
                                sqli_db_syntax_errors += 1
                            else:
                                sqli_framework_crashes += 1
                                if len(sqli_crash_logs) < 3:
                                    # Capture a clean, truncated snippet of the 500 response
                                    clean_body = json_body.replace('\n', ' ').strip()
                                    sqli_crash_logs.append((path, clean_body[:80]))

            except Exception:
                pass

print('\n[1A] ALL CATS FUZZERS TRIGGERING 5XX ERRORS (DYNAMICALLY FETCHED)')
print('-' * 80)
for fuzzer, count in cats_fuzzers_5xx.most_common():
    print(f'  - {fuzzer:<45}: {count:>5} files')

print('\n[1B] CATS 5XX FAULT DYNAMIC CATEGORIZATION')
print('-' * 80)
print(f'  Total 5xx Test Files Analyzed : {total_5xx_files:,}')
for cat, count in cats_categories.most_common():
    pct = (count / max(1, total_5xx_files)) * 100
    print(f'  - {cat:<56}: {count:>5} ({pct:5.1f}%)')

print('\n[1C] CATS VULNERABILITY DEEP-DIVE VERIFICATION')
print('-' * 80)
print('  [SQL INJECTION VERIFICATION]')
print(f'    Total 500 Responses Analyzed           : {sqli_total}')
print(f'    - Framework Parameter Binding Crashes  : {sqli_framework_crashes} ({100*sqli_framework_crashes/max(1,sqli_total):.1f}%)')
if sqli_framework_crashes > 0:
    print('      Inspecting Framework Crash Responses:')
    for i, (p, b) in enumerate(sqli_crash_logs):
        print(f'      [{i+1}] {p:<40} -> Resp: {b}...')
print(f'    - PostgreSQL Syntax Exception (DB Hit) : {sqli_db_syntax_errors} ({100*sqli_db_syntax_errors/max(1,sqli_total):.1f}%)')
print('\n  [IDOR / BOLA VERIFICATION]')
print(f'    Total IDOR Fuzzing Attempts            : {idor_total}')
print(f'    - HTTP 500/403/404 (Failed Exploits)   : {idor_failed_exploits} ({100*idor_failed_exploits/max(1,idor_total):.1f}%)')
print(f'    - HTTP 200 OK (Potential Data Leak)    : {idor_200_count} ({100*idor_200_count/max(1,idor_total):.1f}%)')
if idor_200_count > 0:
    print('      Inspecting HTTP 200 OK Response Bodies:')
    for i, (path, body) in enumerate(idor_200_logs[:5]):
        print(f'      [{i+1}] {path:<40} -> Body: {body}')
    if idor_200_count > 5:
        print(f'      ... (and {idor_200_count - 5} more identical empty responses)')

# ==============================================================================
# 2. SCHEMATHESIS DYNAMIC PARSER & VERIFIER
# ==============================================================================
st_xml_path = 'schemathesis_report.xml'

st_categories = Counter()
st_raw_messages = []
st_5xx_total = 0

if os.path.exists(st_xml_path):
    with open(st_xml_path, 'r', encoding='utf-8', errors='ignore') as f:
        xml_text = f.read()

    failures = re.findall(r'<failure[^>]*>(.*?)</failure>|<error[^>]*>(.*?)</error>', xml_text, re.DOTALL)
    
    for f in failures:
        err_text = str(f[0] or f[1])
        err_lower = err_text.lower()
        
        if 'server error' in err_lower or '500' in err_lower:
            st_5xx_total += 1
            
            # Search specifically for the response body printed by Schemathesis after the 500 code
            resp_match = re.search(r'\[500\] Internal Server Error:\s*(.*?)(?:\n\n|\Z)', err_text, re.DOTALL | re.IGNORECASE)
            
            if resp_match:
                # Clean out the markdown backticks and newlines from the XML text
                snippet = resp_match.group(1).strip().replace('\n', ' ').replace('`', '')
                
                if 'unexpected error occurred' in snippet.lower() or 'internal_error' in snippet.lower():
                    st_raw_messages.append('{"message": "An unexpected error occurred"} (Masked by @ExceptionHandler)')
                    st_categories['Shallow Unhandled Exception (Masked by @ExceptionHandler)'] += 1
                elif 'uuid' in snippet.lower() or 'type' in snippet.lower():
                    st_raw_messages.append(snippet[:80])
                    st_categories['Shallow Invalid Type / Parsing Error'] += 1
                else:
                    st_raw_messages.append(snippet[:80])
                    st_categories['Unhandled Application Exception (Format Mismatch)'] += 1
            else:
                st_raw_messages.append('Generic 500 / Connection Error')
                st_categories['Unhandled Application Exception (Format Mismatch)'] += 1

print('\n[2A] SCHEMATHESIS RAW 500 ERROR MESSAGES (DYNAMICALLY FETCHED)')
print('-' * 80)
msg_counts = Counter(st_raw_messages)
for msg, count in msg_counts.most_common(10):
    print(f'  [{count:>3}x] {msg}')
if len(msg_counts) > 10:
    print(f'  ... and {len(msg_counts) - 10} more message variations.')

print('\n[2B] SCHEMATHESIS 5XX FAULT DYNAMIC CATEGORIZATION')
print('-' * 80)
print(f'  Total 5xx Failures Analyzed   : {st_5xx_total:,}')
if st_5xx_total > 0:
    for cat, count in st_categories.most_common():
        pct = (count / max(1, st_5xx_total)) * 100
        print(f'  - {cat:<56}: {count:>5} ({pct:5.1f}%)')
else:
    print('  [!] No 5xx errors found in schemathesis_report.xml')

print('=' * 80)

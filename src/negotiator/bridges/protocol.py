"""JSON-line protocol runner, compatible with the legacy Python 2.7 bridge."""
from __future__ import print_function

import json
import sys


def serve(driver):
    # SDK status messages go to stderr; stdout contains protocol records only.
    transport = sys.stdout
    sys.stdout = sys.stderr
    seen = {}
    try:
        for line in sys.stdin:
            if len(line) > 1000000:
                break
            message = json.loads(line)
            key = (message['session_id'], message['request_id'])
            fingerprint = json.dumps(message, sort_keys=True)
            response = dict((k, message[k]) for k in ('protocol', 'session_id', 'request_id'))
            try:
                if message['protocol'] != 1:
                    raise ValueError('Unsupported bridge protocol.')
                if key in seen:
                    if seen[key][0] != fingerprint:
                        raise ValueError('Command identity reused with different content.')
                    response = seen[key][1]
                else:
                    # Reserve identity before effects. A failed call cannot be replayed as new.
                    response.update(ok=False, error='Previous attempt has unknown delivery.')
                    seen[key] = (fingerprint, dict(response))
                    result = driver.call(message['operation'], message['payload'])
                    response.update(ok=True, result=result)
                    seen[key] = (fingerprint, dict(response))
                if message['operation'] == 'wrong_identity':
                    response['session_id'] = 'wrong'
            except Exception as exc:
                response.update(ok=False, error=str(exc))
            transport.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + '\n')
            transport.flush()
    finally:
        driver.close()
        sys.stdout = transport

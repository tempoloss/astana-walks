"""Zero-network proof of the 429-handling path in kv_grid_fetch.fetch() (run from repo root).

Records live evidence for SOURCES 21.11: HTTPError branch, FAILED bookkeeping,
429 backoff (4+4*attempt), continue-on-429, for/else exit -> [] without raising.
"""
import sys, urllib.error
sys.path.insert(0, 'collect/recon/round10')
import kv_grid_fetch as m

calls = {'n': 0}
def fake(*a, **k):
    calls['n'] += 1
    raise urllib.error.HTTPError('https://x', 429, 'Too Many Requests', {}, None)
m.urllib.request.urlopen = fake
slept = []
m.time.sleep = lambda s: slept.append(s)

out = m.fetch(51.1325, 71.4039)
assert out == [] and calls['n'] == 3 and m.FAILED.get('51.1325,71.4039') == 429
assert slept[:3] == [4, 8, 12]
print('PASS: 429 path - HTTPError -> FAILED record -> backoff 4+4a -> continue -> for/else -> []')

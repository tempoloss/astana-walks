"""First-party facts (hours, address, phone, description) from the official sites of the places themselves.

Pipeline: inventory (which domains) -> crawl agents (fetch.py helpers, write data/sites/facts/<domain>.json via
store.py) -> verify.py (every snippet re-found in the cached page) -> join.py (branches -> POIs, data/sites/joined.json).
"""

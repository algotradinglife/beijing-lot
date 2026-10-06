"""Pure source parsers shared by the live and research collection clients.

Each module here turns raw provider bytes/text into plain dict rows and performs
no network access, no persistence and no clock reads, so it can be exercised
offline. Fetching lives in ``beidan_backend.transport``; persistence stays with
the caller.
"""

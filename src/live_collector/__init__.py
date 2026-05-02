"""Beidan (北单) Live Collector.

Polls 北单 让球胜平负 bet pages every 5-15 minutes to capture pre-kickoff
3-SP vector and 销量比 (vol_pct) signals that are wiped after settlement.
Also backfills final settlement from the 500.com kaijiang page.
"""

__version__ = "0.1.0"

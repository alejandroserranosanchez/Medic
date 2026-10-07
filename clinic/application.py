"""Cross-domain orchestration lives here later.

Operations must not import finance. Finance must not read operations tables.
When a booking is completed, this module will call both sides in one transaction.
"""

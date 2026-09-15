"""MERGEN GPU executor.

Runs one imaging job at a time from the local spool (`mergen_spool`): it
verifies what the dispatcher delivered, hands it to an imaging adapter and
publishes the result for the dispatcher to upload. It has no network client,
no VPS address and no worker token; the spool is its only channel.
"""

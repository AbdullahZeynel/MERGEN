"""MERGEN GPU job dispatcher.

Pulls one job at a time from the VPS worker control API, hands it to the local
executor through the spool contract (`mergen_spool`) and uploads the result.
It never runs a model, never starts a subprocess and never opens a GPU device;
the worker token exists in this process only.
"""

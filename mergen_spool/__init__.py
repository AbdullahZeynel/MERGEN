"""Local, versioned hand-off between the MERGEN GPU dispatcher and executor.

`contract` names the files and validates their JSON; `fs` holds the atomic
write, bounded read and locking primitives both sides must use. Nothing here
opens a socket or reads a credential.
"""

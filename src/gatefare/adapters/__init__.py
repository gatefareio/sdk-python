"""Framework adapters for popular Python agent stacks.

Each submodule returns descriptors that match the host framework's
expected shape WITHOUT importing the framework — consumers install
their own version and wrap the descriptor we hand them.
"""

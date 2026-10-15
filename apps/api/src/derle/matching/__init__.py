"""Entity resolution: decide which party mentions refer to the same real-world customer.

The pure core (profiles → blocking → scoring → constrained clustering) has no database
dependency, so the benchmark and the service layer run exactly the same code.
"""

"""
Azeotrope APC Runtime Service

Long-running service that executes MPC controllers in real-time.
Connects to plant via OPC UA, calls C++ core for optimization,
and logs everything to SQLite.
"""


def main():
    """Entry point for the runtime service."""
    # TODO: Implement runtime service
    # 1. Load controller configs from repository
    # 2. Initialize OPC UA client
    # 3. Start scheduler for each controller
    # 4. Run event loop
    raise NotImplementedError("Runtime service not yet implemented")


if __name__ == "__main__":
    main()

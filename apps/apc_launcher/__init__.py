"""APC Launcher -- the front door to the Azeotrope APC stack.

A small PySide6 desktop window that knows about all five apps and
spawns each one as a subprocess. Useful when you want to bring up
the whole stack from one place rather than juggling five terminals.

Apps it can launch:
  apc_architect   -- configuration / tuning / simulation studio
  apc_ident       -- step-test identification studio
  apc_runtime     -- headless production controller cycle loop
  apc_historian   -- centralised cycle store + REST query service
  apc_manager     -- operator web console (PCWS equivalent)
"""

"""PyInstaller entry point: the installed app's executable runs this."""
import multiprocessing
import os
import sys

from aion2calc.launcher import main

if __name__ == "__main__":
    for _name in ("stdout", "stderr"):        # the windowed build (and the overlay subprocess) has no console
        if getattr(sys, _name) is None:
            setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))      # noqa: SIM115
    multiprocessing.freeze_support()          # the optimizer uses worker processes
    sys.exit(main())

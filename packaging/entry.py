"""PyInstaller entry point: the installed app's executable runs this."""
import multiprocessing
import sys

from aion2calc.launcher import main

if __name__ == "__main__":
    multiprocessing.freeze_support()          # the optimizer uses worker processes
    sys.exit(main())

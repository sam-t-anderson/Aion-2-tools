"""Experimental player-target kit using mode-specific generic skill data."""
from .generic import build_kit as generic_build_kit, spec_options as generic_spec_options


def spec_options(cd, build):
    return generic_spec_options(cd, build)


def build_kit(build, cd, filler=None):
    return generic_build_kit(build, cd, filler=filler, pvp=True)

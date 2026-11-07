"""Experimental player-target kit using mode-specific generic skill data."""
from .generic import build_kit as generic_build_kit, spec_options as generic_spec_options


def spec_options(cd, build):
    return generic_spec_options(cd, build)


def build_kit(build, cd, filler=None):
    kit = generic_build_kit(build, cd, filler=filler, pvp=True)
    if build.cls == "assassin":
        # Defiance's level-8 chain, Storm Slice: Defiance breaks the crowd control players land (kit.assassin)
        from .assassin import storm_slice
        action = storm_slice(build, cd)
        if action is not None:
            kit.actions[action.key] = action
            kit.policy = [action.key] + [e for e in kit.policy if e != action.key]
    return kit

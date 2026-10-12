"""Multi-monitor-aware restore of a remembered overlay position
(``overlay.resolve_remembered_position``). Keying only by the overall virtual-desktop
box is wrong when monitors are rearranged; this restores by the monitor layout."""
from aion2calc.overlay import resolve_remembered_position as place


FHD = (1920, 1080)


def test_unchanged_layout_keeps_the_exact_position():
    mons = [(0, 0, *FHD)]
    assert place(100, 100, [(0, 0, *FHD)], mons) == (100, 100)


def test_unchanged_layout_drops_a_position_off_every_monitor():
    # Top-left within the margin of the right edge no longer lands grabbably -> None.
    assert place(1900, 100, [(0, 0, *FHD)], [(0, 0, *FHD)]) is None


def test_no_saved_layout_falls_back_to_on_any_monitor():
    # Older saved data (no layout): accept when it lands on a monitor, else fall back.
    assert place(50, 50, None, [(0, 0, *FHD)]) == (50, 50)
    assert place(5000, 50, None, [(0, 0, *FHD)]) is None


def test_added_monitor_leaves_the_unchanged_monitor_position_exact():
    # A second monitor appears; the overlay was on the primary, which is unchanged.
    saved = [(0, 0, *FHD)]
    now = [(0, 0, *FHD), (1920, 0, 1280, 1024)]
    assert place(100, 100, saved, now) == (100, 100)


def test_moved_monitor_reseats_at_the_same_offset_within_it():
    # The overlay was 50/60 into a 1280x1024 secondary; that monitor moved to the left.
    saved = [(0, 0, *FHD), (1920, 0, 1280, 1024)]
    now = [(0, 0, *FHD), (-1280, 0, 1280, 1024)]
    assert place(1970, 60, saved, now) == (-1230, 60)   # -1280 + 50, 0 + 60


def test_reseat_clamps_within_the_monitor_margin():
    # Same-size monitor moved; an offset past the right edge clamps to leave a margin.
    saved = [(0, 0, 1000, 1000)]
    now = [(100, 0, 1000, 1000)]
    assert place(980, 500, saved, now) == (1060, 500)   # 100+1000-40 = 1060


def test_host_monitor_gone_falls_back():
    # The monitor the overlay was on no longer exists at that size -> fall back.
    assert place(100, 100, [(0, 0, *FHD)], [(0, 0, 2560, 1440)]) is None


def test_no_current_monitors_falls_back():
    assert place(100, 100, [(0, 0, *FHD)], []) is None


def test_malformed_rectangles_are_ignored():
    # Zero/negative sizes and short tuples are dropped, not crashed on.
    assert place(100, 100, [(0, 0, *FHD)], [(0, 0, 0, 0), (0, 0, *FHD)]) == (100, 100)

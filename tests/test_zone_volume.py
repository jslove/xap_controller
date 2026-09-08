"""XAPZone.async_set_volume_level: every output is set from the requested level.

setPropGain returns the achieved proportion relative to the channel it wrote, so a loop
that feeds its return value forward sets each output after the first from the previous
channel's read-back. These tests only bite when the read-back differs from the request --
with a faithful device and one shared MAXGAIN the round trip is a fixed point and the
buggy code produces identical calls. So the fake below clamps per channel, which is
exactly the condition per-channel ceilings introduce.
"""

import asyncio

import pytest


class FakeHass:
    async def async_add_executor_job(self, fn):
        return fn()


class FakeConn:
    """setPropGain that clamps to a per-channel ceiling, as a unit with per-channel
    MAXGAIN does: the value that lands is not the value requested."""

    def __init__(self, ceilings=None, live=True):
        self.conn_id = "fake"
        self.connectionLive = 1 if live else 0
        self.ceilings = ceilings or {}
        self.calls = []

        class _Lock:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *a):
                return False

        self._lock = _Lock()

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0):
        self.calls.append((unitCode, channel, gain))
        return min(gain, self.ceilings.get((unitCode, channel), 1.0))


def zone(component, conn, outputs, name="Kitchen"):
    return component.XAPZone(FakeHass(), conn, {}, name, outputs)


def test_every_output_is_set_from_the_requested_level(component):
    # Output 1 clamps to 0.5; output 2 must still be asked for 0.8, not for 0.5.
    conn = FakeConn(ceilings={(0, 1): 0.5})
    z = zone(component, conn, [1, 2])
    asyncio.run(z.async_set_volume_level(0.8))
    assert conn.calls == [(0, 1, 0.8), (0, 2, 0.8)]


def test_a_clamp_does_not_propagate_down_a_six_channel_zone(component):
    conn = FakeConn(ceilings={(1, 9): 0.25})
    z = zone(component, conn, ["1:9", "1:10", "1:11", "1:12"], name="Family Surround")
    asyncio.run(z.async_set_volume_level(0.9))
    assert [g for _u, _c, g in conn.calls] == [0.9, 0.9, 0.9, 0.9]


def test_the_reported_level_follows_the_first_output(component):
    # _get_volume_level reads _outputs[0]; the setter must agree with it.
    conn = FakeConn(ceilings={(0, 1): 0.5, (0, 2): 0.9})
    z = zone(component, conn, [1, 2])
    asyncio.run(z.async_set_volume_level(0.8))
    assert z._volume == 0.5


def test_an_unclamped_zone_reports_what_was_asked_for(component):
    conn = FakeConn()
    z = zone(component, conn, [3, 4])
    asyncio.run(z.async_set_volume_level(0.1))
    assert z._volume == 0.1
    assert conn.calls == [(0, 3, 0.1), (0, 4, 0.1)]


def test_channels_repeated_in_a_zone_are_each_written(component):
    # Kitchen is [3, 4, 3, 4] on the rig this was written against: the repeats are
    # deliberate and must not be collapsed the way the cache pre-warm collapses reads.
    conn = FakeConn()
    z = zone(component, conn, [3, 4, 3, 4])
    asyncio.run(z.async_set_volume_level(0.2))
    assert conn.calls == [(0, 3, 0.2), (0, 4, 0.2), (0, 3, 0.2), (0, 4, 0.2)]


def test_outputs_on_a_chained_unit_keep_their_unit(component):
    conn = FakeConn()
    z = zone(component, conn, [7, "1:7"])
    asyncio.run(z.async_set_volume_level(0.3))
    assert conn.calls == [(0, 7, 0.3), (1, 7, 0.3)]


def test_an_offline_zone_writes_nothing(component):
    conn = FakeConn(live=False)
    z = zone(component, conn, [1, 2])
    asyncio.run(z.async_set_volume_level(0.8))
    assert conn.calls == []

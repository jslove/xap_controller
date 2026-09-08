"""MAXGAIN pre-warm: seeding XAPX00's cache for zone output channels at setup.

The point of the pre-warm is *when* the MAX read happens, not whether it happens, so
these tests are mostly about which channels get read and which calls are made.
"""

import asyncio

import pytest


class FakeHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, fn):
        return fn()


class FakeLock:
    def __init__(self):
        self.held = 0
        self.max_held = 0

    def __enter__(self):
        self.held += 1
        self.max_held = max(self.max_held, self.held)
        return None

    def __exit__(self, *a):
        self.held -= 1
        return False


class FakeConn:
    def __init__(self, connected=True, fail_on=()):
        self.connectionLive = 1 if connected else 0
        self.reads = []
        self.writes = []
        self.fail_on = set(fail_on)
        self._lock = FakeLock()

    def getMaxGain(self, channel, group="I", unitCode=0, **kwargs):
        self.reads.append((unitCode, channel, group, kwargs.get("stereo")))
        if (unitCode, channel) in self.fail_on:
            raise RuntimeError("no response")
        return 20.0

    def setMaxGain(self, *a, **k):
        self.writes.append((a, k))


class FakeZone:
    """Only the two things the pre-warm touches: the output list and the parser."""

    def __init__(self, outputs):
        self._outputs = list(outputs)

    def parse_output(self, output):
        if isinstance(output, int):
            return 0, output
        if isinstance(output, str):
            if ":" in output:
                unit, chan = output.split(":")
                return int(unit), int(chan)
            if output.isdigit():
                return 0, int(output)
        raise Exception("Invalid Output String")


def run(component, conn, zones):
    hass = FakeHass()
    asyncio.run(component._prewarm_max_gain(hass, conn, zones))
    return conn


def test_every_zone_output_channel_is_read(component):
    conn = run(component, FakeConn(), [FakeZone([1, 2]), FakeZone(["1:5", "1:6"])])
    assert [(u, c) for u, c, _g, _s in conn.reads] == [(0, 1), (0, 2), (1, 5), (1, 6)]


def test_channels_are_read_once_even_when_listed_twice(component):
    # A zone doubling a channel to feed it twice - Kitchen is [3, 4, 3, 4] on the rig
    # this was written against - must not cost two round trips for the same channel.
    conn = run(component, FakeConn(), [FakeZone([3, 4, 3, 4])])
    assert [(u, c) for u, c, _g, _s in conn.reads] == [(0, 3), (0, 4)]


def test_the_same_channel_on_two_units_is_not_deduplicated(component):
    conn = run(component, FakeConn(), [FakeZone([7]), FakeZone(["1:7"])])
    assert [(u, c) for u, c, _g, _s in conn.reads] == [(0, 7), (1, 7)]


def test_reads_are_output_group_and_suppress_the_stereo_repeat(component):
    conn = run(component, FakeConn(), [FakeZone([3])])
    assert conn.reads == [(0, 3, "O", 0)]


def test_nothing_is_written_to_the_unit(component):
    conn = run(component, FakeConn(), [FakeZone([1, 2])])
    assert conn.writes == []


def test_an_offline_unit_is_left_alone(component):
    conn = run(component, FakeConn(connected=False), [FakeZone([1, 2])])
    assert conn.reads == []


def test_a_channel_that_does_not_answer_does_not_stop_the_rest(component):
    conn = run(component, FakeConn(fail_on=[(0, 2)]), [FakeZone([1, 2, 3])])
    assert [(u, c) for u, c, _g, _s in conn.reads] == [(0, 1), (0, 2), (0, 3)]


def test_a_malformed_output_is_skipped_rather_than_failing_setup(component):
    conn = run(component, FakeConn(), [FakeZone([1, "kitchen", 2])])
    assert [(u, c) for u, c, _g, _s in conn.reads] == [(0, 1), (0, 2)]


def test_no_zones_means_no_connection_use(component):
    conn = run(component, FakeConn(), [])
    assert conn.reads == [] and conn._lock.max_held == 0


def test_the_batch_takes_the_connection_lock_once(component):
    conn = run(component, FakeConn(), [FakeZone([1, 2, 3, 4])])
    assert conn._lock.max_held == 1 and conn._lock.held == 0

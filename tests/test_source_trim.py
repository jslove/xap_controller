"""Source input trim: opt-in exposure, and setting every input from the same request."""

import asyncio

import pytest


class FakeConn:
    conn_id = "test"
    stereo = 0
    connectionLive = True

    def __init__(self, maxgain=None):
        # maxgain maps channel -> that channel's ceiling in dB
        self.maxgain = maxgain or {}
        self.set_calls = []

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0, stereo=1):
        self.set_calls.append((channel, gain))
        # what the unit reports back is a proportion of *this* channel's MAXGAIN, so two
        # inputs with different ceilings return different numbers for the same request
        return gain * self.maxgain.get(channel, 1.0)


def make_source(component, conn, inputs, allow_trim=False):
    src = component.XAPSource(None, conn, "Src", inputs, allow_trim=allow_trim)
    src._xap = _run
    return src


async def _run(fn):
    return fn()


def test_trim_is_not_exposed_by_default(component):
    src = make_source(component, FakeConn(), [9])
    assert not (src.supported_features & component.MPEF.VOLUME_SET)


def test_trim_is_exposed_when_opted_in(component):
    src = make_source(component, FakeConn(), [9], allow_trim=True)
    assert src.supported_features & component.MPEF.VOLUME_SET


def test_mute_and_power_are_available_either_way(component):
    for allow in (False, True):
        src = make_source(component, FakeConn(), [9], allow_trim=allow)
        assert src.supported_features & component.MPEF.VOLUME_MUTE
        assert src.supported_features & component.MPEF.TURN_ON


def test_every_input_is_set_from_the_requested_level(component):
    """The bug: the second input used to be set from the first one's readback.

    The first channel's ceiling has to differ from unity or the bug is invisible - with
    maxgain 1.0 the readback equals the request and the wrong value is the right one.
    """
    conn = FakeConn(maxgain={9: 0.5, 10: 0.5})
    src = make_source(component, conn, [9, 10], allow_trim=True)
    asyncio.run(src.async_set_volume_level(0.8))
    assert [gain for _, gain in conn.set_calls] == [0.8, 0.8]


def test_a_single_input_is_unaffected(component):
    conn = FakeConn(maxgain={9: 1.0})
    src = make_source(component, conn, [9], allow_trim=True)
    asyncio.run(src.async_set_volume_level(0.6))
    assert conn.set_calls == [(9, 0.6)]


def test_the_reported_level_follows_the_first_input(component):
    """_get_volume_level reads _inputs[0], so the setter must agree with it."""
    conn = FakeConn(maxgain={9: 0.5, 10: 0.5})
    src = make_source(component, conn, [9, 10], allow_trim=True)
    asyncio.run(src.async_set_volume_level(0.8))
    assert src.volume_level == pytest.approx(0.4)

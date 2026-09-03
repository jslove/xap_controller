# async-library — a proof-of-concept that was set aside

This branch drops the executor and lock wrappers and calls the XAPX00 library
directly: `await XAPX00.create(...)`, then 17 `await self._xapx00.<method>()`
calls. It requires XAPX00's `async-library` branch and cannot run against the
XAPX00 master line — `create()` and the async methods do not exist there.

**`master` is the live line.** Do not deploy this branch.

## Why it was stopped

The decision was made on the library side, not here: making XAPX00 async forces
an event loop on everyone who uses it outside Home Assistant, and the rewrite
also silently dropped ~46 public methods that this component happens not to call.
See `ASYNC-NOTES.md` on XAPX00's `async-library` branch for the full reasoning.

The relevant point for this repo: **wrapping a synchronous library in
`hass.async_add_executor_job` is the sanctioned Home Assistant pattern, not a
workaround.** That is what master does, and removing the executor hop saves
microseconds against a ~10 ms device round trip.

## State as of 2026-09-03

- Pins XAPX00 tag `2026.05.13-async` (the head of that repo's `async-library`
  branch), so the pair is installable as designed. Before 2026-09-03 it still
  pinned the *sync* tag `2026.04.22` and would have failed at setup on the first
  `await XAPX00.create(...)`.
- `master` has since moved ahead: it pins XAPX00 `2026.09.03`, which caches
  MAXGAIN and halves the round trips on the volume path. Reviving this branch
  means porting that forward.
- Two things master does that this branch's design removes, both correct here:
  the external `_lock` monkey-patch (locking is internal to the async library)
  and the `_xap` executor helper.

## Known bug carried on both branches

`async_set_volume_level` rebinds its `volume` argument from the device
read-back inside the loop, so every channel after the first is set to the
previous channel's round-tripped value:

```python
volume = await self._xapx00.setPropGain(XOUT, volume, ...)
```

Present in both the Source (~line 390) and Zone (~line 633) setters, and
`async_mute_volume` has the same shape with `self._isMuted`. Measured drift is
at most 0.005 dB and is a fixed point under device quantisation, so it is not
audible today. It becomes real if the device ever clamps a requested value, or
if channels within one zone have different MAXGAIN. Fix is one line each: assign
the read-back to a different name.

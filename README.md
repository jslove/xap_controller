## The XAPController platform allows the use of a ClearOne Converge Pro v1, XAP 400 or 800 unit as an audio routing matrix with HomeAssistant.

At this time, it is set up only for routing audio, not for use with microphones.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.xap_controller/
(no docs there until release)

There are two components in the platform: output Zones and input Sources.  The input sources are assumed to be type I inputs, the output zones type O outputs.

The system can have multple units linked together.  The configured Sources and Zones can specify only the channel for input or output, in which case it is assumed they are on unit 0.  They can also specify the unit, and optionally, for sources, an expansion bus that the source is also mapped to, so that it can be used on other units in the systems.  In this case, list the unit:channel of the source, and then the expansion channel and optinoally expansion group (E or P).  When sources or zones are specified with units and expansion buses, the items should be listed as a string of the format "<Unit#>:<Channel#>:<Expansion Bus Channel Letter>:<Expansion BUs Group>".  See below for an example.  For the expansion bus setup to work the matrix needs to have the sources mapped to the expansin channels through the G-Ware software.

**The `stereo` option is deprecated and will be removed in a future release.**  If stereo=1, the module takes each action twice, once on the listed source/zone number and again on the source/zone + 1.  It overlaps the explicit multi-channel list below, and the two are unsafe in combination: a zone listed as `[3, 4]` with `stereo: 1` writes crosspoints for 3&4 and then 4&5, and channel 5 belongs to some other zone.  List each channel explicitly instead:

```yaml
# deprecated
stereo: 1
zones:
  'Office':
    - 3

# preferred
stereo: 0
zones:
  'Office':
    - 3
    - 4
```

See [issue #23](https://github.com/jslove/xap_controller/issues/23) for the removal plan.

For each source or zone, multiple channels can be listed, as a list.  If multiple channels are listed for a source and an output, they will be paired sequentially, source item 1 to zone item 1, source item 2 to zone item 2, etc.  If there are more source channels than zone channels, only the first channels in the source will be used.  If there are more channels in a zone than in the source being applied ot it, the source channels will be repeated.  This multiple channel apporach can be used to handle stereo (instead of the stereo=1 approach), but it was added to handle surround sound sources / zones. The XAP system will mix multiple source channels applied to one output zone channel.

The platform will create individual media_player controls for each source and zone.  Each source will be shown with a volume slider, adjusting the gain for that input.  Each Zone will be shown with a dropbox to select from the available sources and a volume slider to adjust the gain for that output zone.

Basic configuration
```
media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     stereo: 1 # 1 or 0, default is 0, recommend explicitly listing sterero channels
     baud: 38400 #default
     XAPType: XAP800 # XAP800 or XAP400, default is XAP800
     zones:
       'Office':
         - 1
       'Kitchen':
         - 3
       'Outside':
         - 5
       'Upstairs':
         - 7
       'Living/Dining/Library':
         - 9
       'WorkRoom':
         - "2:1"
     sources:
       'Home Audio':
         - 9
       'Family TV Audio':
         - 11
```

Multi-unit example
```
media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     stereo: 0
     baud: 38400
     zones:
       'Office':
         - "1:1"
         - "1:2"
       'Kitchen':
         - "1:3"
         - "1:4"
        'Family Room Surround':
         - "2:1"
         - "2:2"
         - "2:3"
         - "2:4"
         - "2:1"
         - "2:2"
         # Family Room Surround has no center speaker, so list the two front
         # speakers at the end and map the center channel to each of them

     sources:
       'Home Audio':
         - "1:9:O:E"
         - "1:10:P:E"
       'Family TV Surround Audio':
         - "2:1:V:E"
         - "2:2:W:E"
         - "2:3:X:E"
         - "2:4:Y:E"
         - "2:5:Z:E"
         - "2:5:Z:E"
         # Family Room Surround has no center channel, so list the center channel twice at the end,  
         # then it will be connected to the last 2 itens in the zone channel list
```

* zones: a list of output zone names, with a list of one or more outputs for each zone name. 
* sources: a list of source names, with a list of one or more sources per source name.
   sources are listed as either a digit, indicating the input channel on unit 0, or else a string of the format:  "<unit#>:<input#>:<bus letter>:<bus type>. Bus and Bus type are optional, but are needed if using more than 1 unit and you want a source to be available on outputs in other units.
* path: serial device path (can be a virtual serial port, using socat for example)
* name: the name of the platform instance
* stereo: **deprecated** — 1=stereo, 0=mono.  If stereo=1, each action will be performed twice on the input (output) and input+1 (output)+1.  List channels explicitly instead; see above.
* baud: baud rate of serial port, 38400 (default), 9600, 19200, 57600
* XAPType: XAP unit type, eithr XAP800 (default) or XAP400

Setup Notes:
For the sources, set the gain levels in the Clearone Console app.  They are very sensitive and should be calibrated to 0db.  I have removed the ability to change the source gain levels from the UI to prevent mis-configuation.  It can be added back through the source gode by adding MPEF.VOLUME_SET to the SOURCE capability list (if you need it, for example if you don't have the Console app available).

## Raw command access (`xap_controller.send_command`)

For hands-on work on the unit â€” reading `LABEL`, `MTRX`, `MAX`, or trying anything the
entities do not model â€” call the service rather than opening the serial port from another
process. `XAPCommand` owns the device address, the terminator, the response parsing and
the lock, so going through it cannot collide with the entities mid-frame.

```yaml
action: xap_controller.send_command
data:
  command: GAIN 7 O
response_variable: reply
```

Returns `{"command": "GAIN 7 O", "response": ["GAIN 7 O -33.00 A", ...]}`. Pass only the
command body; the `#5<unit>` prefix and the `\r` terminator are added for you.

- `unit` (default 0) addresses other XAPs on the expansion chain.
- `return_count` (default 16) is how many trailing tokens of the reply to keep. It is a
  tail, not a limit, so too small a value silently drops the front of the answer â€” at 2,
  `LABEL 5 O` comes back as `- Patio` with the `3L` missing. The default is past the
  longest reply seen; asking for more tokens than arrive just returns what arrived.
- A command the unit refuses comes back as `{"command": ..., "error": ...}` rather than
  raising, because a rejection is a normal result when probing an unfamiliar unit.
## Max gain per output channel (safety ceiling)

`MAXGAIN` is a per-channel ceiling in the XAP hardware: `GAIN` cannot be set above it.
It is *also* the reference that Home Assistant's `volume_level` is measured against â€”
`getPropGain`/`setPropGain` express level as a ratio of it, so `volume_level: 1.0`
means "this channel's MAXGAIN".

An unconfigured unit leaves MAXGAIN at the **+20 dB factory maximum** on every channel,
which is bad twice over:

- **Safety.** A slider dragged to 100% drives the output at +20 dB. On ceiling speakers
  that is not a volume anyone intended.
- **Usability.** Real listening levels are far below that, so they crowd into the very
  bottom of the slider. On the unit this was written against, four zones sitting between
  âˆ’22.5 and âˆ’33 dB all landed under **1%** â€” the whole useful range inside two pixels of
  travel.

Set the optional **Max gain** field on the Sources & Zones step to a JSON object mapping
output channel to a dB ceiling:

```json
{"1": -15, "2": -15, "3": -15, "4": -15, "5": -15, "6": -15, "7": -15, "8": -15}
```

With a âˆ’15 dB ceiling, 100% means âˆ’15 dB, and a zone at âˆ’22.5 dB shows as about 42%.

- Values must be between âˆ’65 and +20 dB; channels you leave out are not touched.
- Leave the field blank to keep the old behaviour and not write MAXGAIN at all.
- The ceilings are re-applied on every setup, so a change made in G-Ware or from the
  front panel is restored the next time Home Assistant starts.
- **Lowering a ceiling pulls that channel's GAIN down to it â€” but the integration does
  that, not the hardware.** The XAP leaves an existing level exactly where it was, above
  its own stated maximum. On 2026-09-06 a reload wrote all eight ceilings to âˆ’15.00 while
  the outputs stayed between âˆ’7.50 and âˆ’13.34; `volume_level` is a ratio against MAXGAIN,
  so those zones reported values greater than 1.0 â€” `zone_kitchen_dining` read **2.371**, a
  slider at 237% â€” and every slider move wrote dB against a ceiling the levels had never
  been chosen for. `_apply_max_gain` now reads each listed channel back after writing its
  ceiling and clamps anything above it, which is why a configured channel cannot report
  more than 1.0. The clamp only ever reduces a level, never raises one. A channel you left
  out of the config is not clamped, and can still read above 1.0.

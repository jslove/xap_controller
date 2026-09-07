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
For the sources, set the gain levels in the Clearone Console app.  They are very sensitive and should be calibrated to 0db.  Source gain is not adjustable from the UI by default.  If the Console app is not a practical way to set trim, tick **Allow source input gain to be set from the UI** on the Sources & Zones step and the source entities gain a level control.  Leave it off unless you need it: input trim is a calibration control, and anything that treats a `media_player` as a speaker — a broad `media_player.volume_set`, a voice assistant, a HomeKit/Alexa/Google bridge — will reach it once it looks like a volume.

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

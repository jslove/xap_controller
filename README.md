
## The XAPController platform allows the use of a ClearOne XAP 400 or 800 unit as an audio routing matrix.

At this time, it is set up only for routing audio, not for use with microphones.

Support for interfacing with ClearOne XAP800 and XAP400 units via serial port.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.xap_controller/


There are two components in the platform: output Zones and input Sources.  The input sources are assumed to be XAP type I inputs, 
the output zones type O outpurs.  The system can assume that the channels are set up for stereo, so that there are 2 channels paired 
together.  If stereo=1, the module will take each action twice, once on the listed source/zone number and again on the source/zone + 1.

For each source or zone, indicate the channel to use on the XAP unit.

The platform will create individual media_player controls for each source and zone.  Each source will be shown with a volume slider, adjusting the 
gain for that input.  Each Zone will be shown with a dropbox to select from the available zones and a volume slider to adjust the gain for that output.

Basic configuration:
'''
media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     scan_interval: 30
     stereo: 1
     baud: 9600
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
         - 11
     sources:
       'Home Audio': 9
       'Family TV Audio': 11
'''

zones: a list of output zone names, with a list one or more outputs for each zone
sources: a list of source names, with a list of one source input number per source name.
path: serial device path (can be a virtual serial port, using socat for example)
name: the name of the platform instance
stereo: 1=stereo, 0=mono  If stereo=1, each action will be performed twice on the output and output+1
baud: baud rate of serial port, default=38400
scan_interval: how often to scane the unit for changes

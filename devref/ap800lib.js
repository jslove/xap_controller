/////////////////////////////////////////////////////////////////////////////
//
// Gentner/ClearOne AP800 Automatic Mixer Control Library
// Copyright (C) 2005 Kade Consulting, LLC.  All rights reserved.
// Author: Dan Rudman (dantelope)
//
// This script may be freely copied and modified so long as it carries a
// reference to the above copyright.  Any modifications to this script
// must use this license and, thus, must itself be freely copyable and 
// modifiable under the same terms.
//
// A special thanks to Paul Koslow for all of his support in the area of
// voice recognition and for recommending the AP800 hardware to me.
//
/////////////////////////////////////////////////////////////////////////////

//
// Global Constants - DO NOT MODIFY
//
var AP800_CMD = "#1";
var AP800_INI = "AP800.ini";
var AP800_LOCATION_PREFIX = "AP800";
var AP800_UNIT_TYPE = 1;
var SETTINGS_GROUP = "Settings";
var ERROR_LEVEL = "Error";
var WARNING_LEVEL = "Warning";
var INFO_LEVEL = "Info";
var DEBUG_LEVEL = "Debug";
var EOM = "\r";
var STATUS_ON = 2;
var STATUS_OFF = 3;
var FLAG_NO_LOGGING = 0x0008;
var FLAG_HIDDEN_FROM_VIEW = 0x0020;

//
// Global Constants - Modify to suit
//
function DEVICE_MIC_MUTE_STATUS(n)		{ return "Microphone #" + n + " Mute Status"; }
var DEVICE_MAXMICS									= "Max Number of Microphones";


//
// Main entry point; currently does nothing
//
function main()
{
}

//
// Retrieves AP800 settings stored in the Config/AP800.ini file.  This
// function creates a settings object to contain all of the values.
//
function getSettings()
{
	var settings = new Object();
	
	settings.comPort = hs.GetINISetting( SETTINGS_GROUP, "serial_port", "1", AP800_INI );	
	settings.baudRate = hs.GetINISetting( SETTINGS_GROUP, "baud_rate", "9600", AP800_INI );
	if ( settings.baudRate != 9600 &&
	     settings.baudRate != 19200 &&
	     settings.baudRate != 38400 )
	{
		// Default to 9600 baud if the INI file value is invalid
		settings.baudRate = 9600;
	}
	
	// Fixed values for communicating with the AP800: 8 bits, 1 stop bit, no parity
	settings.byteLength = 8;
	settings.stopBits = 1;
	settings.parity = "N";
		
	// Debugging level specification [0 = No debug/info, 1 = simple info, 2 = detailed info
	settings.logLevel = hs.GetINISetting( SETTINGS_GROUP, "log_level", "0", AP800_INI );
	
	return settings;
}

//
// Connects HomeSeer with the AP800 via the RS-232 serial port.  Note
// that if there is already a connection this method will have no effect
// on the serial connection, although you will get an error in the logs.
//
function connect()
{
	var settings = getSettings();
	
	if ( settings.logLevel > 0 )
	{
		hs.WriteLog( INFO_LEVEL, "Connecting to AP800 at " + settings.baudRate + " baud..." );
	}
		
	var errTxt = hs.OpenComPort( 
		settings.comPort, 
		settings.baudRate + ","
		+ settings.parity + ","
		+ settings.byteLength + ","
		+ settings.stopBits + ",",
		1, 
		"ap800lib.js", 
		"handle_event", 
		EOM );

	if ( errTxt != undefined && errTxt.length > 0 )
	{
		hs.WriteLog( ERROR_LEVEL, "Unable to open serial port connection to AP800 (check your INI settings): " + errTxt );
	}
	else if ( settings.logLevel > 0 )
	{
		hs.WriteLog( INFO_LEVEL, "AP800 connected" );
	}
	
	// Ensure connectivity by requesting the UID of the first unit
	requestUniqueId(0);
}

//
// Disconnect HomeSeer from the AP800 by closing down the serial port.  If
// the port was already closed, this method will have no effect.
//
function disconnect()
{
	var settings = getSettings();
	if ( settings.logLevel > 0 )
	{
		hs.WriteLog( INFO_LEVEL, "Disconnecting from AP800..." );
	}
	
	hs.CloseComPort( settings.comPort );
	
	if ( settings.logLevel > 0 )
	{
		hs.WriteLog( INFO_LEVEL, "AP800 disconnected." );
	}
}

//
// This is the callback method HomeSeer will send carriage-return-terminated
// data to for handling.  The data will be in the AP800 format, as specified
// by the manual.  It checks the unit type to ensure that the message is
// meant for the AP800, ignoring anything that wasn't.  Then, it provides
// a case-by-case handling statement for each command that could be received.
//
// For each case to be handled, a new handler method should be created and
// called from here.  The handler should take the unit code and the list of
// elements.  Each individual handler method can shift off the elements
// in accordance with its specifications.
//
// Typically, you will create a device to go with whatever you are interested
// in.  
//
function handle_event( data )
{
	var settings = getSettings();
	
	// All responses are anchored by the hash mark.  Sometimes, there is
	// data prior to this point -- we wish to ignore that data.
	var indexOfStart = data.indexOf( '#' );
	if ( indexOfStart < 0 )
	{
		// Oops, there was no hash mark to anchor from!
		hs.WriteLog( WARNING_LEVEL, "Ignoring unexpected data received from AP800: " + data );
		return;
	}
	
	// Extract the formatted reply
	data = data.substring( indexOfStart );
	
	if ( settings.logLevel > 1 )
	{
		hs.WriteLog( DEBUG_LEVEL, "AP800 DATA IN [" + data + "]" );
	}
	
	// Parse up the formatted reply into a list of elements
	var elems = data.split( " " );
	
	// The device ID (Unit Type + Unit ID) is the first element in any reply
	var deviceId = elems.shift();
	var unitType = deviceId.charAt( 1 );
	
	if ( unitType != AP800_UNIT_TYPE )
	{
		// We only care about AP800 replies -- anything else we'll ignore. 
		if ( settings.logLevel > 1 )
		{
			hs.WriteLog( WARNING_LEVEL, "Ignoring data not meant for the AP800: " + data );
		}
		return;
	}
	
	var unitCode = deviceId.charAt( 2 );
	var command = elems.shift();

	// Branch to individual handlers for known replies based on the command name
	switch( command )
	{
		case "AAMB":
			break;
		case "AGC":
			break;
		case "AMBLVL":
			break;
		case "BAUD":
			break;
		case "CHAIRO":
			break;
		case "DECAY":
			break;
		case "DFLTM":
			break;
		case "EC":
			break;
		case "ERL":
			break;
		case "ERLE":
			break;
		case "EQ":
			break;
		case "FLOW":
			break;
		case "FMP":
			break;
		case "FPP":
			break;
		case "GAIN":
			break;
		case "GATE":
			break;
		case "GMODE":
			break;
		case "GRATIO":
			break;
		case "HOLD":
			break;
		case "LFP":
			break;
		case "LMO":
			break;
		case "LVL":
			break;
		case "MASTER":
			break;
		case "MDMODE":
			break;
		case "MEQ":
			break;
		case "MHP":
			break;
		case "MINIT":
			break;
		case "MLINE":
			break;
		case "MMAX":
			handleMmaxReply( unitCode, elems );
			break;
		case "MPASS":
			break;
		case "MREF":
			break;
		case "MTRX":
			break;
		case "MUTE":
			handleMuteReply( unitCode, elems );
			break;
		case "NLP":
			break;
		case "NOM":
			break;
		case "OFFA":
			break;
		case "PAA":
			break;
		case "PCMD":
			break;
		case "PEVNT":
			break;
		case "PP":
			break;
		case "PRESET":
			break;
		case "REFSEL":
			break;
		case "TOUT":
			break;
		case "UID":
			break;
		case "VER":
			break;
		default:
			if ( settings.logLevel > 0 )
			{
				hs.WriteLog( WARNING_LEVEL, "Unknown reply: ignoring" );
			}
	}
}

//
// Handler for an MMAX request.  Places the value returned into
// the associated device.
//
// Note the use of unit code to create the unique Location for
// the AP800.
//
function handleMmaxReply( unitCode, elems )
{
	var mmax = elems.shift();
	var settings = getSettings();
	var deviceName = createLocation( unitCode ) + " " + DEVICE_MAXMICS;
	
	hs.SetDeviceStringByName( deviceName, mmax, true );	
}

//
// Handler for a MUTE request.  Places the value returned into
// the associated device.
//
// Note the use of unit code to create the unique Location for
// the AP800.
//
function handleMuteReply( unitCode, elems )
{
	var channel = elems.shift();
	var channelType = elems.shift();
	var isMuted = ( elems.shift() == "1" );
	
	// Currently we'll only handle microphones -- add other i/o later
	if ( channelType.toUpperCase() != "I" || parseInt( channel ) == 0 )
	{
		return;
	}
	
	var settings = getSettings();
	var deviceName = createLocation( unitCode ) + " " + DEVICE_MIC_MUTE_STATUS(channel);
	var deviceCode = hs.GetDeviceCode( deviceName );
	
	hs.WriteLog( "Debug", "deviceName[" + deviceName + "], deviceCode[" + deviceCode + "], isMuted=" + isMuted );
	
	hs.SetDeviceStatus( deviceCode, isMuted ? STATUS_ON : STATUS_OFF );	
}


//
// Modifies the state of the adaptive ambient for the specified microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
// isEnabled - true to enable, false to disable
//
function enableAdaptiveAmbient( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " AAMB " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM);
}

//
// Requests the state of the adaptive ambient for the specified microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
//
function requestAdaptiveAmbient( unitCode, channel )
{
	send( AP800_CMD + unitCode + " AAMB " + channel + EOM);
}

//
// Modifies the state of the automatic gain control (AGC)
// for the specified microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
// isEnabled - true to enable, false to disable
//
function enableAutoGainControl( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " AGC " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM);
}

//
// Toggles the state of the automatic gain control (AGC)
// for the specified microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
//
function toggleAutoGainControl( unitCode, channel )
{
	send( AP800_CMD + unitCode + " AGC " + channel + " 2" + EOM);
}

//
// Requests the state of the automatic gain control (AGC)
// for the specified microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
//
function requestAutoGainControl( unitCode, channel )
{
	send( AP800_CMD + unitCode + " AGC " + channel + EOM);	
}

//
// Sets the fixed ambient level of the specified AP800.  This
// value will only be set if adaptive ambient is disabled.
//
// unitCode - the unit code of the target AP800
// levelInDb - the ambient level in dB (0 to -70)
//
function setAmbientLevel( unitCode, levelInDb )
{
	// Ensure compliance with level boundary conditions
	if ( levelInDb > 0 )
	{
		levelInDb = 0;
	}
	else if ( levelInDb < -70 )
	{
		levelInDb = -70;
	}
	
	send( AP800_CMD + unitCode + " AMBLVL " + levelInDb + EOM);
}

//
// Requests the fixed ambient level of the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestAmbientLevel( unitCode )
{
	send( AP800_CMD + unitCode + " AMBLVL " + EOM);
}

//
// Sets the baud rate for the RS232 port on the specified AP800.
//
// unitCode - the unit code of the target AP800
// baudRate - the baud rate (9600, 19200, or 38400)
//
function setBaudRate( unitCode, baudRate )
{
	var baudRateCode;
	
	// Ensure compliance with level boundary conditions
	switch( baudRate )
	{
		case 9600:
			baudRateCode = 1;
			break;
		case 19200:
			baudRateCode = 2;
			break;
		case 38400:
			baudRateCode = 3;
			break;
		default:
			baudRateCode = 1;		
	}
	
	send( AP800_CMD + unitCode + " BAUD " + baudRateCode + EOM);
}

//
// Requests the baud rate for the RS232 port on the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestBaudRate( unitCode )
{
	send( AP800_CMD + unitCode + " BAUD " + EOM);
}

//
// Modifies the state of the chairman override for the specified
// microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
// isEnabled - true to enable, false to disable
//
function enableChairmanOverride( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " CHAIRO " + channel + ( isEnabled ? "1" : "0" ) + EOM);
}

//
// Requests the state of the chairman override for the specified
// microphone(s).
//
// unitCode - the unit code of the target AP800
// channel - 1-8 for specific mic channel, or * for all mics
//
function requestChairmanOverride( unitCode, channel )
{
	send( AP800_CMD + unitCode + " CHAIRO " + channel + EOM);	
}

//
// Modifies the decay rate for the specified AP800.
//
// unitCode - the unit code of the target AP800
// decayRate - the rate of decay
//                1 = slow, 2 = medium, 3 = fast
//
function setDecayRate( unitCode, decayRate )
{
	// Ensure compliance with level boundary conditions
	if ( decayRate < 1 )
	{
		decayRate = 1;
	}
	else if ( decayRate > 3 )
	{
		decayRate = 3;
	}
	
	send( AP800_CMD + unitCode + " DECAY " + decayRate + EOM);	
}

//
// Requests the decay rate for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestDecayRate( unitCode )
{
	send( AP800_CMD + unitCode + " DECAY " + EOM);	
}

//
// Modifies the default meter for the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the input or output to set as the meter
//           (1-8 or A-D)
// isInput - true if the channel is an input, false
//           if the channel is an output.
function setDefaultMeter( unitCode, channel, isInput )
{
	send( AP800_CMD + unitCode + " DFLTM " + channel + " " + ( isInput ? "I" : "O" ) + EOM);	
}

//
// Requests the default meter for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestDefaultMeter( unitCode )
{
	send( AP800_CMD + unitCode + " DFLTM " + EOM);	
}

//
// Enables or disables the echo canceller for the specified
// channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// isEnabled - true to enable the channel, false to disable
//
function enableEchoCanceller( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " EC " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM);	
}

//
// Requests the status of the echo canceller for the specified
// channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel
//
function requestEchoCanceller( unitCode, channel )
{
	send( AP800_CMD + unitCode + " EC " + channel + EOM);	
}

//
// Requests the status of the echo return loss
// for the specified channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel
//
function requestEchoReturnLoss( unitCode, channel )
{
	send( AP800_CMD + unitCode + " ERL " + channel + EOM);	
}

//
// Requests the status of the echo return loss enhancement
// for the specified channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel
//
function requestEchoReturnLossEnhancement( unitCode, channel )
{
	send( AP800_CMD + unitCode + " ERLE " + channel + EOM);	
}

//
// Enables or disables the equalizer for the specified
// channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// isEnabled - true to enable the channel, false to disable
//
function enableEqualizer( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " EQ " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM);	
}

//
// Toggles the equalizer for the specified
// channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function toggleEqualizer( unitCode, channel )
{
	send( AP800_CMD + unitCode + " EQ " + channel + " 2" + EOM);	
}

//
// Requests the status of the equalizer for the specified
// channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestEqualizer( unitCode, channel )
{
	send( AP800_CMD + unitCode + " EQ " + channel + EOM);	
}

//
// Enables or disables hardware flow control for the specified
// AP800.
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable the channel, false to disable
//
function enableHardwareFlowControl( unitCode, isEnabled )
{
	send( AP800_CMD + unitCode + " FLOW " + ( isEnabled ? "1" : "0" ) + EOM);	
}

//
// Requests the status of the hardware flow control for the specified
// AP800.
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable the channel, false to disable
//
function requestHardwareFlowControl( unitCode )
{
	send( AP800_CMD + unitCode + " FLOW " + EOM);	
}

//
// Enables or disables first microphone priority mode for 
// the specified AP800.
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable the channel, false to disable
//
function enableFirstMicPriorityMode( unitCode, isEnabled )
{
	send( AP800_CMD + unitCode + " FMP " + ( isEnabled ? "1" : "0" ) + EOM);	
}

//
// Requests the first microphone priority mode for 
// the specified AP800.
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable the channel, false to disable
//
function requestFirstMicPriorityMode( unitCode )
{
	send( AP800_CMD + unitCode + " FMP " + EOM);	
}

//
// Sets the front panel passcode for the specified AP800.
//
// unitCode - the unit code of the target AP800
// passcode - the passcode to use for the front panel
//
function setFrontPanelPasscode( unitCode, passcode )
{
	send( AP800_CMD + unitCode + " FPP " + passcode + EOM);	
}

//
// Requests the front panel passcode for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestFrontPanelPasscode( unitCode )
{
	send( AP800_CMD + unitCode + " FPP " + EOM);	
}

//
// Sets the gain on the specified channel for the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, A-D, 1-2, or * for all)
// channelType - the type of channel (I for input, O for output,
//                                    S for subbus)
// level - the amount of gain to apply in dB (-20 to 20).
// isRelative - true if the level is specified relative to current,
//              false if it's an absolute setting.
//
function setGain( unitCode, channel, channelType, level, isRelative )
{	
	send( AP800_CMD + unitCode + " GAIN " + channel + " " + channelType + " " + level + ( isRelative ? "R" : "A" ) + EOM);
}

//
// Requests the gain on the specified channel for the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, A-D, 1-2, or * for all)
// channelType - the type of channel (I for input, O for output,
//                                    S for subbus)
//
function requestGain( unitCode, channel, channelType )
{
	send( AP800_CMD + unitCode + " GAIN " + channel + " " + channelType + EOM);
}

//
// Requests the gating status for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestGate( unitCode )
{
	send( AP800_CMD + unitCode + " GATE " + EOM);	
}

//
// Sets the gating mode on the specified channel for the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// mode - the gating mode
//        1 = AUTO
//				2 = MANUAL ON
//				3 = MANUAL OFF
//				4 = OVERRIDE ON
//				5 = OVERRIDE OFF
//
function setGatingMode( unitCode, channel, mode )
{
	send( AP800_CMD + unitCode + " GMODE " + channel + " " + mode + EOM);		
}

//
// Requests the gating mode on the specified channel for the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestGatingMode( unitCode, channel )
{
	send( AP800_CMD + unitCode + " GMODE " + channel + EOM);			
}

//
// Sets the gating ratio for the specified AP800.  The
// ratio is limited to 0-50; values outside the boundary
// will be anchored to the boundaries.
//
// unitCode - the unit code of the target AP800
// gateRatioInDb - the gating ratio in dB (0-50)
//
function setGateRatio( unitCode, gateRatioInDb )
{
	// Ensure compliance with level boundary conditions
	if ( gateRatioInDb < 0 )
	{
		gateRatioInDb = 0;
	}
	else if ( gateRatioInDb > 50 )
	{
		gateRatioInDb = 50;
	}
	
	send( AP800_CMD + unitCode + " GRATIO " + channel + " " + gateRatioInDb + EOM);		
}

//
// Requests the gating ratio for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestGateRatio( unitCode )
{
	send( AP800_CMD + unitCode + " GRATIO" + EOM);			
}

//
// Sets the hold time for the specified AP800.  The
// value is limited to 100-8000; values outside the boundary
// will be anchored to the boundaries.
//
// unitCode - the unit code of the target AP800
// holdTimeInMs - the hold time in milliseconds (100-8000)
//
function setHoldTime( unitCode, holdTimeInMs )
{
	// Ensure compliance with level boundary conditions
	if ( holdTimeInMs < 100 )
	{
		holdTimeInMs = 100;
	}
	else if ( holdTimeInMs > 8000 )
	{
		holdTimeInMs = 8000;
	}
	
	send( AP800_CMD + unitCode + " HOLD " + holdTimeInMs + EOM);		
}

//
// Locks or unlocks the front panel of the specifid AP800
//
// unitCode - the unit code of the target AP800
// isLocked - true to lock, false to unlock
//
function setFrontPanelLock( unitCode, isLocked )
{
	send( AP800_CMD + unitCode + " LFP " + ( isLocked ? "1" : "0" ) + EOM);			
}

//
// Toggles the front panel lock of the specified AP800
//
// unitCode - the unit code of the target AP800
//
function toggleFrontPanelLock( unitCode )
{
	send( AP800_CMD + unitCode + " LFP 2" + EOM);			
}

//
// Requests the front panel lock status of the specified AP800
//
// unitCode - the unit code of the target AP800
//
function requestFrontPanelLock( unitCode )
{
	send( AP800_CMD + unitCode + " LFP" + EOM);			
}

//
// Sets the last microphone on mode of the specified AP800
//
// unitCode - the unit code of the target AP800
// mode - the last mic on mode
//				0 = OFF
//				1 = Microphone #1
//				2 = Last Microphone On
//
function setLastMicOnMode( unitCode, mode )
{
	send( AP800_CMD + unitCode + " LMO " + mode + EOM);				
}

//
// Requests the last microphone on mode of the specified AP800
//
// unitCode - the unit code of the target AP800
//
function requestLastMicOnMode( unitCode )
{
	send( AP800_CMD + unitCode + " LMO" + EOM);				
}

//
// Requests the level of the target channel on the specified AP800
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, A-D)
// channelType - the target channel type 
//							 I = Input, 
//							 O = Output, 
//							 A = Adaptive Ambient Meter
//
function requestLevel( unitCode, channel, channelType )
{
	send( AP800_CMD + unitCode + " LVL " + channel + " " + channelType + EOM);				
}

//
// Sets the master mode of the specified AP800
//
// unitCode - the unit code of the target AP800
// mode - the master mode
//				1 = Master Single
//				2 = Dual Mixer
//				3 = Slave
//				4 = Master Linked
//
function setMasterMode( unitCode, mode )
{
	send( AP800_CMD + unitCode + " MASTER " + mode + EOM);				
}

//
// Requests the master mode of the specified AP800
//
// unitCode - the unit code of the target AP800
//
function requestMasterMode( unitCode )
{
	send( AP800_CMD + unitCode + " MASTER " + EOM);					
}

//
// Enables or disables the modem mode of the specified AP800
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable, false to disable
//
function enableModemMode( unitCode, isEnabled )
{
	send( AP800_CMD + unitCode + " MDMODE " + ( isEnabled ? "1" : "0" ) + EOM);				
}

//
// Sets the microphone equalizer adjustment of the target channel
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// band - H=High, M=Medium, L=Low
// eqValue - the eq value (-12 to 12)
//
function setMicEqualizerAdjustment( unitCode, channel, band, eqValue )
{
	send( AP800_CMD + unitCode + " MEQ " + channel + " " + band + " " + eqValue + EOM);				
}

//
// Requests the microphone equalizer adjustment of the target channel
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// band - H=High, M=Medium, L=Low
//
function requestMicEqualizerAdjustment( unitCode, channel, band )
{
	send( AP800_CMD + unitCode + " MEQ " + channel + " " + band + EOM);					
}

//
// Enables or disables the microphone high pass filter of the target channel
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// isEnabled - true to enable, false to disable
//
function enableMicHighPassFilter( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " MHP " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM);					
}

//
// Requests the microphone high pass filter of the target channel
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestMicHighPassFilter( unitCode, channel )
{
	send( AP800_CMD + unitCode + " MHP " + channel + " " + EOM);					
}

//
// Sets the modem initialization string of the specified AP800.
//
// unitCode - the unit code of the target AP800
// initString - the string to use when initializing the modem
//
function setModemInitString( unitCode, initString )
{
	send( AP800_CMD + unitCode + " MINIT " + initString + EOM );						
}

//
// Sets the microphone input gain for the target channel 
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// gain - the gain value to use
//				1 = 55dB
//				2 = 25dB
//				3 = 0dB (line level)
//
function setMicInputGain( unitCode, channel, gain )
{
	send( AP800_CMD + unitCode + " MLINE " + channel + " " + gain + EOM );							
}

//
// Requests the microphone input gain for the target channel 
// of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestMicInputGain( unitCode, channel )
{
	send( AP800_CMD + unitCode + " MLINE " + channel + EOM );							
}

//
// Sets the maxmimum number of active microphones  
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// maxMics - the maximum number of mics that will be active
//           at the same time (1-8, or 0 for no limit)
//
function setMaxActiveMics( unitCode, maxMics )
{
	if ( maxMics < 0 )
	{
		maxMics = 0;
	}
	else if ( maxMics > 8 )
	{
		maxMics = 8;
	}
	
	send( AP800_CMD + unitCode + " MMAX " + maxMics + EOM );								
}

//
// Requests the maxmimum number of active microphones  
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestMaxActiveMics( unitCode )
{
	send( AP800_CMD + unitCode + " MMAX" + EOM );								
}

//
// Sets the modem password for the specified AP800.
//
// unitCode - the unit code of the target AP800
// modemPassword - the modem password
//
function setModemModePassword( unitCode, modemPassword )
{
	send( AP800_CMD + unitCode + " MPASS " + modemPassword + EOM );								
}

//
// Sets the microphone echo canceller reference channel
// for the target channel of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// ecRef - the reference channel
//				 1 = EC Ref 1
//				 2 = EC Ref 2
//
function setMicEchoCancellerReference( unitCode, channel, ecRef )
{
	send( AP800_CMD + unitCode + " MREF " + channel + " " + ecRef + EOM );									
}

//
// Requests the microphone echo canceller reference channel
// for the target channel of the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestMicEchoCancellerReference( unitCode, channel )
{
	send( AP800_CMD + unitCode + " MREF " + channel + EOM );									
}

//
// Sets the routing matrix for the target channel of
// the specified AP800.
//
// unitCode - the unit code of the target AP800
// inChannel - the target input channel (1-25; see
//             page 64 of the AP800 manual for
//             details)
// outMix - a hex value specifying the output mix as a
//          series of bit flags (again, see pg 64).
//
function setRoutingMatrix( unitCode, inChannel, outMix )
{
	send( AP800_CMD + unitCode + " MTRX " + inChannel + " " + outMix + EOM );										
}

//
// Mutes the target channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8 or *, A-D, 1-2)
// channelType - I=Input, O=Output, S=Subbus
// isMuted - true to mute, false to unmute
//
function mute( unitCode, channel, channelType, isMuted )
{
	send( AP800_CMD + unitCode + " MUTE " + channel + " " + channelType + " " + ( isMuted ? "1" : "0" ) + EOM );									
}

//
// Toggles the muting of the target channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8 or *, A-D, 1-2)
// channelType - I=Input, O=Output, S=Subbus
//
function toggleMute( unitCode, channel, channelType )
{
	send( AP800_CMD + unitCode + " MUTE " + channel + " " + channelType + " 2" + EOM );										
}

//
// Requests the mute status of the target channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8 or *, A-D, 1-2)
// channelType - I=Input, O=Output, S=Subbus
//
function requestMuteStatus( unitCode, channel, channelType )
{
	send( AP800_CMD + unitCode + " MUTE " + channel + " " + channelType + EOM );	
}

//
// Sets the nonlinear processing (NLP) mode of the target channel
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// nlpMode - the NLP mode to use
//					 0 = OFF
//					 1 = Soft
//				   2 = Medium
//					 3 = Aggressive
//
function setNonlinearProcessingMode( unitCode, channel, nlpMode )
{
	send( AP800_CMD + unitCode + " NLP " + channel + " " + nlpMode + EOM );											
}

//
// Requests the nonlinear processing (NLP) mode of the target channel
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestNonlinearProcessingMode( unitCode, channel )
{
	send( AP800_CMD + unitCode + " NLP " + channel + EOM );											
}

//
// Enables or disables NOM attenuation for the target channel
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// isEnabled - true to enable NOM, false to disable
//
function enableNumberOpenMicsAttenuation( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " NOM " + channel + " " + ( isEnabled ? "1" : "0" ) + EOM );												
}

//
// Requests the NOM attenuation for the target channel
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestNumberOpenMicsAttenuation( unitCode, channel )
{
	send( AP800_CMD + unitCode + " NOM " + channel + EOM );													
}

//
// Sets the off attenuation for the specified AP800. The
// value is limited to 0-50; values outside the boundary
// will be anchored to the boundaries.
//
// unitCode - the unit code of the target AP800
// attenuation - the attenuation in dB (0-50)
//
function setOffAttenuation( unitCode, attenuation )
{
	if ( attenuation < 0 )
	{
		attenuation = 0;
	}
	else if ( attenuation > 50 )
	{
		attenuation = 50;
	}
	
	send( AP800_CMD + unitCode + " OFFA " + attenuation + EOM );													
}

//
// Requests the off attenuation for the specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestOffAttenuation( unitCode )
{
	send( AP800_CMD + unitCode + " OFFA" + EOM );													
}

//
// Enables or disables PA adaptive mode for the 
// specified AP800.
//
// unitCode - the unit code of the target AP800
// isEnabled - true to enable, false to disable
//
function enablePaAdaptiveMode( unitCode, isEnabled )
{
	send( AP800_CMD + unitCode + " PAA " + ( isEnabled ? "1" : "0" ) + EOM );														
}

//
// Requests the PA adaptive mode for the 
// specified AP800.
//
// unitCode - the unit code of the target AP800
//
function requestPaAdaptiveMode( unitCode )
{
	send( AP800_CMD + unitCode + " PAA" + EOM );															
}

//
// Specifies the command to be executed when the
// GPIO pin/control occurs.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
// command - the command to execute (any of LFP,
//				   PRESET, MUTE, GAIN, AGC, EQ, GMODE,
//					 or CHAIRO)
//
function setControlPinCommand( unitCode, pinLocation, command )
{
	send( AP800_CMD + unitCode + " PCMD " + pinLocation + " " + command + EOM );																	
}

//
// Clears any commands set for the the
// GPIO pin/control specified.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
//
function clearControlPinCommand( unitCode, pinLocation )
{
	setControlPinCommand( unitCode, pinLocation, "CLEAR" );
}

//
// Requests the command to be executed when the
// GPIO pin/control occurs.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
//
function requestControlPinCommand( unitCode, pinLocation )
{
	send( AP800_CMD + unitCode + " PCMD " + pinLocation + EOM );																		
}

//
// Specifies the command to be executed when the
// GPIO pin/status occurs.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
// command - the command to execute (any of LFP,
//				   PRESET, MUTE, GAIN, AGC, EQ, GMODE,
//					 or CHAIRO)
//
function setStatusPinCommand( unitCode, pinLocation, command )
{
	send( AP800_CMD + unitCode + " PEVNT " + pinLocation + " " + command + EOM );																		
}

//
// Clears any commands set for the the
// GPIO pin/status specified.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
//
function clearStatusPinCommand( unitCode, pinLocation )
{
	setStatusPinCommand( unitCode, pinLocation, "CLEAR" );
}

//
// Requests the command to be executed when the
// GPIO pin/status occurs.
//
// unitCode - the unit code of the target AP800
// pinLocation - the pin location (see pg 67 of the
//               AP800 manual for specifications)
//
function requestControlPinCommand( unitCode, pinLocation )
{
	send( AP800_CMD + unitCode + " PEVNT " + pinLocation + EOM );																		
}

//
// Enables or disables phantom power for the target channel
// on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
// isEnabled - true to enable, false to disable
//
function enablePhantomPower( unitCode, channel, isEnabled )
{
	send( AP800_CMD + unitCode + " PP " + channel + ( isEnabled ? "1" : "0" ) + EOM );
}

//
// Requests the enable status of phantom power for 
// the target channel on the specified AP800.
//
// unitCode - the unit code of the target AP800
// channel - the target channel (1-8, or * for all)
//
function requestPhantomPower( unitCode, channel )
{
	send( AP800_CMD + unitCode + " PP " + channel + EOM );
}

//
// Causes the AP800 to swap its settings for the given
// preset.
//
// unitCode - the unit code of the target AP800
// preset - the preset to switch to (1-6)
//
function usePreset( unitCode, preset )
{
	send( AP800_CMD + unitCode + " PRESET " + preset + EOM );	
}

//
// Requests the current preset in use for the specified
// AP800.
//
// unitCode - the unit code of the target AP800
//
function requestPreset( unitCode )
{
	send( AP800_CMD + unitCode + " PRESET" + EOM );		
}

//
// Sets the microphone echo canceller reference
// output for the specified AP800.
//
// unitCode - the unit code of the target AP800
// ecRef - the desired reference channel
//				 1 = EC Ref 1
//				 2 = EC Ref 2
//				 3 = G-Link EC Ref bus
// output - the output channel to reference
//					(1-8, A-D, E to select G-Link Ref Bus, or F
//           to select NONE)
//
function setMicEchoCancellerReferenceOutput( unitCode, ecRef, output )
{
	send( AP800_CMD + unitCode + " REFSEL " + ecRef + " " + output + EOM );		
}

//
// Requests the microphone echo canceller reference
// output for the specified AP800.
//
// unitCode - the unit code of the target AP800
// ecRef - the desired reference channel
//				 1 = EC Ref 1
//				 2 = EC Ref 2
//				 3 = G-Link EC Ref bus
//
function requestMicEchoCancellerReferenceOutput( unitCode, ecRef )
{
	send( AP800_CMD + unitCode + " REFSEL " + ecRef + EOM );		
}

//
// Sets the screen timeout in minutes for the specified
// AP800. The value is limited to 0-50; values outside the boundary
// will be anchored to the boundaries.
//
// unitCode - the unit code of the target AP800
// timeInMinutes - the timeout value in minutes (1-15, or 0 to disable)
//
function setScreenTimeout( unitCode, timeInMinutes )
{
	if ( timeInMinutes < 0 )
	{
		timeInMinutes = 0;
	}
	else if ( timeInMinutes > 15 )
	{
		timeInMinutes = 15;
	}
	
	send( AP800_CMD + unitCode + " TOUT " + timeInMinutes + EOM );		
}

//
// Requests the screen timeout in minutes for the specified
// AP800.
//
// unitCode - the unit code of the target AP800
//
function requestScreenTimeout( unitCode )
{
	send( AP800_CMD + unitCode + " TOUT" + EOM );		
}

//
// Requests the unique ID of the target AP800.  This is a hex
// value preprogrammed at the factory.
//
// unitCode - the unit code of the target AP800
//
function requestUniqueId( unitCode )
{
	send( AP800_CMD + unitCode + " UID" + EOM );			
}

//
// Requests the firmware version of the target AP800.
//
// unitCode - the unit code of the target AP800
//
function requestVersion( unitCode )
{
	send( AP800_CMD + unitCode + " VER" + EOM );			
}


//
// Sends the specified data to the AP800
//
function send( data )
{
	var settings = getSettings();
	
	if ( settings.logLevel > 1 )
	{
		hs.WriteLog( DEBUG_LEVEL, "AP800 DATA OUT [" + data + "]" );
	}
	hs.SendToComPort( settings.comPort, data );
}

//
// Use this method to call functions in this script from a HomeSeer
// action.  HomeSeer actions only permit a single argument to be
// passed in.  This method will call the desired function properly.
//
// args - a string in the form "method[|arg1][[|arg2]...]"
//
// Example: hsScriptCaller( "requestPhantomPower|0|1" )
//
function hsScriptCaller( args )
{
	var argv = args.split('|');
	var s = argv.shift() + "(";
	
	while( argv.length > 0 )
	{
		// Automatically quote all arguments.  If they're numeric,
		// Javascript will allow us to deal with them effectively
		// once we're inside the target method.
		s = s.concat( "\"" ).concat( argv.shift() ).concat( "\"" );
		if ( argv.length > 0 )
		{
			// More arguments -- add a comma and move on
			s = s.concat( ", " );
		}
	}
	
	s = s.concat( ")" );
	
	hs.WriteLog( DEBUG_LEVEL, "script [" + s + "]" );
	eval( s );
}

//
// Creates a unique HS Location for the AP800 specified by the
// unit code.  The first AP800 would be at, for example,
// "AP800_0".
//
// unitCode - the unit code of the AP800
//
function createLocation( unitCode )
{
	return AP800_LOCATION_PREFIX + " ID#" + unitCode;
}

//
// Translates ERROR replies from the AP800 into a human-readable
// description of the problem.  Useful for error reporting.
//
function getHumanErrorDescription( errorMsg )
{
	switch( errorMsg )
	{
		case "ERROR 1":
			return "The address is not valid/out of range or an invalid character";
		case "ERROR 2":
			return "Could not extract a command from the string received";
		case "ERROR 3":
			return "Serial overrun";
		case "ERROR 4":
			return "N/A - reserved for later use";
		case "ERROR 5":
			return "Invalid parameter";
		case "ERROR 6":
			return "Unrecognized command";
		default:
			return "Unknown error - no description found";
	}
}

//
// Initializing function -- you should technically only need to execute
// this once to set up all the necessary events and devices.  Naturally,
// if you're anything like me, you'll probably end up running it a bunch
// of times until you get it juuuuuust right.
//
function setupAll()
{
	createAllMissingEvents();
	createAllMissingDevices();
	connect();
}

//
// Utility function to create any needed events that are missing from HomeSeer
//
// Currently this is not as automated as I'd like.  You'll need to manually
// adjust parameters here in accordance with your setup.
//
function createAllMissingEvents()
{
	// TODO
}

//
// Utility function to create any needed devices that are missing from HomeSeer
//
// Currently this is not as automated as I'd like.  You'll need to manually
// adjust parameters here in accordance with your setup.  Pay close attention
// to the createLocation() calls if you have more than one AP800.
//
function createAllMissingDevices()
{
	createMissingDevice( DEVICE_MAXMICS, "z50", "Virtual", createLocation(0) );
	
	var device;
	for( var i=1; i<=8; i++ )
	{
		device = createMissingDevice( DEVICE_MIC_MUTE_STATUS(i), "z5" + i, "Virtual", createLocation(0) );
	}
}

//
// Utility function to quickly create a device of the specified
// parameters.  If the device already exists, this method will simply
// return without doing anything.  By default, all devices are
// created as Status Only.  If you want something else you can change it
// with the return value.
//
function createMissingDevice( deviceName, address, deviceType, deviceLocation )
{
	var settings = getSettings();
	
	if ( hs.GetDeviceRefByName( deviceName ) > 0 || hs.GetDeviceRef( address ) > 0 )
	{
		if ( settings.logLevel > 0 )
		{
			hs.WriteLog( INFO_LEVEL, "Duplicate device found (address: " + address + ", name: " + deviceName + ") - skipping creation." );
		}
		return null;
	}
	
	var deviceRef = hs.NewDeviceRef( deviceName );
	var device = hs.GetDeviceByRef( deviceRef );
	var x10addr = getX10Address( address );
	
	device.hc = x10addr.houseCode;
	device.dc = x10addr.deviceCode;
	device.location = deviceLocation;
	device.misc = FLAG_NO_LOGGING | FLAG_HIDDEN_FROM_VIEW;
	device.dev_type_string = "Status Only";

	return device;
}

//
// Utility function that breaks an X10 address string (e.g., "H10") into
// its constituent house code and device code (e.g., "H" and "10").
//
function getX10Address( addressString )
{
	if ( addressString == undefined ||
	     addressString == null ||
	     addressString.length < 2 )
	{
		return null;
	}
	
	var x10addr = new Object();
		
	x10addr.houseCode = addressString.charAt( 0 );
	x10addr.deviceCode  = addressString.substring( 1 );
	
	return x10addr;
}
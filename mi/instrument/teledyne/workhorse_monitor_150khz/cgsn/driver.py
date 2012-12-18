"""
@package mi.instrument.teledyne.workhorse_monitor_150khz.cgsn.driver
@file marine-integrations/mi/instrument/teledyne/workhorse_monitor_150khz/cgsn/driver.py
@author Lytle Johnson
@brief Driver for the cgsn
Release notes:

moving to teledyne
"""

__author__ = 'Lytle Johnson'
__license__ = 'Apache 2.0'

import re
import time
import string
import ntplib

from mi.core.log import get_logger ; log = get_logger()

from mi.core.common import BaseEnum
from mi.core.instrument.instrument_protocol import CommandResponseInstrumentProtocol
from mi.core.instrument.instrument_fsm import InstrumentFSM
from mi.core.instrument.instrument_driver import SingleConnectionInstrumentDriver
from mi.core.instrument.instrument_driver import DriverEvent
from mi.core.instrument.instrument_driver import DriverAsyncEvent
from mi.core.instrument.instrument_driver import DriverProtocolState
from mi.core.instrument.instrument_driver import DriverParameter
from mi.core.instrument.instrument_driver import ResourceAgentState
from mi.core.instrument.data_particle import DataParticle
from mi.core.instrument.data_particle import DataParticleKey
from mi.core.instrument.data_particle import CommonDataParticleType
from mi.core.instrument.chunker import StringChunker


# newline.
NEWLINE = '\n'

# default timeout.
TIMEOUT = 10

CZ_REGEX = r'Powering Down '
CZ_REGEX_MATCHER = re.compile(CZ_REGEX)

BREAK_REGEX = r'\[BREAK Wakeup A\]\nWorkHorse Broadband ADCP Version \d+[.]\d+\nTeledyne RD Instruments \(c\) 1996-2\d{3}\nAll Rights Reserved.\n>'
BREAK_REGEX_MATCHER = re.compile(BREAK_REGEX)

ERR_REGEX = r'ERR \d{3}:  NUMERAL EXPECTED\n>'
ERR_REGEX_MATCHER = re.compile(ERR_REGEX)


###
#    Driver Constant Definitions
###

class DataParticleType(BaseEnum):
    """
    Data particle types produced by this driver
    """
    RAW = CommonDataParticleType.RAW

class InstrumentCmds(BaseEnum):
    """
    Device specific commands
    Represents the commands the driver implements and the string that must be sent to the instrument to
    execute the command.
    """
    SETSAMPLING = 'setsampling'
    DISPLAY_STATUS = 'ds'
    QUIT_SESSION = 'qs'
    DISPLAY_CALIBRATION = 'dc'
    START_LOGGING = 'start'
    STOP_LOGGING = 'stop'
    SET = 'set'
    GET = 'get'
    TAKE_SAMPLE = 'ts'
    INIT_LOGGING = 'initlogging'
#--------------------------------------
    BREAK = 'break'
    SET = 'set'
    GET = 'get'
    POWER_DOWN = 'CZ'
    CLEAR_ERROR_STATUS_WORD = 'CY'
    CLEAR_FAULT_LOG = 'FC'
    DISPLAY_SYSTEM_CONFIGURATION = 'PS0'
    DISPLAY_TRANSFORMATION_MATRIX = 'PS3'
    DISPLAY_FAULT_LOG = 'FD'
    BUILT_IN_TEST = 'PT200'
    OUTPUT_CALIBRATION_DATA = 'AC'
    SET_COLLECTION_MODE = 'CF'
    START_DEPLOYMENT = 'CS'
    SAVE_SETUP_TO_RAM = 'CK'
    RETRIEVE_DATA_ENSEMBLE = 'CE'

class ProtocolState(BaseEnum):
    """
    Instrument protocol states
    """
    UNKNOWN = DriverProtocolState.UNKNOWN
    COMMAND = DriverProtocolState.COMMAND
    AUTOSAMPLE = DriverProtocolState.AUTOSAMPLE
    DIRECT_ACCESS = DriverProtocolState.DIRECT_ACCESS
    TEST = DriverProtocolState.TEST
    CALIBRATE = DriverProtocolState.CALIBRATE

class ProtocolEvent(BaseEnum):
    """
    Protocol events
    """
    ENTER = DriverEvent.ENTER
    EXIT = DriverEvent.EXIT
    GET = DriverEvent.GET
    SET = DriverEvent.SET
    DISCOVER = DriverEvent.DISCOVER
    START_DIRECT = DriverEvent.START_DIRECT
    STOP_DIRECT = DriverEvent.STOP_DIRECT
    ACQUIRE_SAMPLE = DriverEvent.ACQUIRE_SAMPLE
    START_AUTOSAMPLE = DriverEvent.START_AUTOSAMPLE
    STOP_AUTOSAMPLE = DriverEvent.STOP_AUTOSAMPLE
    EXECUTE_DIRECT = DriverEvent.EXECUTE_DIRECT
    CLOCK_SYNC = DriverEvent.CLOCK_SYNC
    ACQUIRE_STATUS = DriverEvent.ACQUIRE_STATUS

class Capability(BaseEnum):
    """
    Protocol events that should be exposed to users (subset of above).
    """
    ACQUIRE_SAMPLE = ProtocolEvent.ACQUIRE_SAMPLE
    START_AUTOSAMPLE = ProtocolEvent.START_AUTOSAMPLE
    STOP_AUTOSAMPLE = ProtocolEvent.STOP_AUTOSAMPLE
    CLOCK_SYNC = ProtocolEvent.CLOCK_SYNC
    ACQUIRE_STATUS  = ProtocolEvent.ACQUIRE_STATUS

class Parameter(DriverParameter):
    """
    Device parameters
    """
    # DS
    DEVICE_VERSION = 'DEVICE_VERSION' # str,
    SERIAL_NUMBER = 'SERIAL_NUMBER' # str,
    INSTRUMENT_ID = 'INSTRUMENT_ID'
    TRANSMIT_POWER = 'TRANSMIT_POWER'
    SPEED_OF_SOUND = 'SPEED_OF_SOUND'
    SALINITY = 'SALINITY'
    TIME_PER_BURST = 'TIME_PER_BURST'
    ENSEMBLE_PER_BURST = 'ENSEMBLE_PER_BURST'
    TIME_PER_ENSEMBLE = 'TIME_PER_ENSEMBLE'
    TIME_OF_FIRST_PING = 'TIME_OF_FIRST_PING'
    TIME_OF_FIRST_PING_Y2K = 'TIME_OF_FIRST_PING_Y2K'
    TIME_BETWEEN_PINGS = 'TIME_BETWEEN_PINGS'
    SET_REAL_TIME_CLOCK = 'SET_REAL_TIME_CLOCK'
    SET_REAL_TIME_CLOCK_Y2K = 'SET_REAL_TIME_CLOCK_Y2K'
    BUFFERED_OUTPUT_PERIOD = 'BUFFERED_OUTPUT_PERIOD'
    FALSE_TARGET_THRESHOLD_MAXIMUM = 'FALSE_TARGET_THRESHOLD_MAXIMUM'
    MODE_1_BANDWIDTH_CONTROL = 'MODE_1_BANDWIDTH_CONTROL'
    LOW_CORRELATION_THRESHOLD = 'LOW_CORRELATION_THRESHOLD'
    DATA_OUT = 'DATA_OUT'
    ERROR_VELOCITY_THRESHOLD = 'ERROR_VELOCITY_THRESHOLD'
    BLANK_AFTER_TRANSMIT = 'BLANK_AFTER_TRANSMIT'
    CLIP_DATA_PAST_BOTTOM = 'CLIP_DATA_PAST_BOTTOM'
    RECEIVER_GAIN_SELECT = 'RECEIVER_GAIN_SELECT'
    WATER_REFERENCE_LAYER = 'WATER_REFERENCE_LAYER'
    NUMBER_OF_DEPTH_CELLS = 'NUMBER_OF_DEPTH_CELLS'
    PINGS_PER_ENSEMBLE = 'PINGS_PER_ENSEMBLE'
    DEPTH_CELL_SIZE = 'DEPTH_CELL_SIZE'
    TRANSMIT_LENGTH = 'TRANSMIT_LENGTH'
    PING_WEIGHT = 'PING_WEIGHT'
    AMBIGUITY_VELOCITY = 'AMBIGUITY_VELOCITY'

class Prompt(BaseEnum):
    """
    Device i/o prompts..
    """

class InstrumentCommand(BaseEnum):
    """
    Instrument command strings
    """
    SETSAMPLING = 'setsampling'
    DISPLAY_STATUS = 'ds'
    QUIT_SESSION = 'qs'
    DISPLAY_CALIBRATION = 'dc'
    START_LOGGING = 'start'
    STOP_LOGGING = 'stop'
    SET = 'set'
    GET = 'get'
    TAKE_SAMPLE = 'ts'
    INIT_LOGGING = 'initlogging'
#--------------------------------------
    BREAK = 'break'
    SET = 'set'
    GET = 'get'
    POWER_DOWN = 'CZ'
    CLEAR_ERROR_STATUS_WORD = 'CY'
    CLEAR_FAULT_LOG = 'FC'
    DISPLAY_SYSTEM_CONFIGURATION = 'PS0'
    DISPLAY_TRANSFORMATION_MATRIX = 'PS3'
    DISPLAY_FAULT_LOG = 'FD'
    BUILT_IN_TEST = 'PT200'
    OUTPUT_CALIBRATION_DATA = 'AC'
    SET_COLLECTION_MODE = 'CF'
    START_DEPLOYMENT = 'CS'
    SAVE_SETUP_TO_RAM = 'CK'
    RETRIEVE_DATA_ENSEMBLE = 'CE'


###############################################################################
# Data Particles
###############################################################################


###############################################################################
# Driver
###############################################################################

class InstrumentDriver(SingleConnectionInstrumentDriver):
    """
    InstrumentDriver subclass
    Subclasses SingleConnectionInstrumentDriver with connection state
    machine.
    """
    def __init__(self, evt_callback):
        """
        Driver constructor.
        @param evt_callback Driver process event callback.
        """
        #Construct superclass.
        SingleConnectionInstrumentDriver.__init__(self, evt_callback)

    ########################################################################
    # Superclass overrides for resource query.
    ########################################################################

    def get_resource_params(self):
        """
        Return list of device parameters available.
        """
        return Parameter.list()

    ########################################################################
    # Protocol builder.
    ########################################################################

    def _build_protocol(self):
        """
        Construct the driver protocol state machine.
        """
        self._protocol = Protocol(Prompt, NEWLINE, self._driver_event)


###########################################################################
# Protocol
###########################################################################

class Protocol(CommandResponseInstrumentProtocol):
    """
    Instrument protocol class
    Subclasses CommandResponseInstrumentProtocol
    """
    def __init__(self, prompts, newline, driver_event):
        """
        Protocol constructor.
        @param prompts A BaseEnum class containing instrument prompts.
        @param newline The newline.
        @param driver_event Driver process event callback.
        """
        # Construct protocol superclass.
        CommandResponseInstrumentProtocol.__init__(self, prompts, newline, driver_event)

        # Build protocol state machine.
        self._protocol_fsm = InstrumentFSM(ProtocolState, ProtocolEvent,
                            ProtocolEvent.ENTER, ProtocolEvent.EXIT)

        # Add event handlers for protocol state machine.
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.ENTER, self._handler_unknown_enter)
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.EXIT, self._handler_unknown_exit)
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.DISCOVER, self._handler_unknown_discover)
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.START_DIRECT, self._handler_command_start_direct)

        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.ENTER, self._handler_command_enter)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.EXIT, self._handler_command_exit)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.START_DIRECT, self._handler_command_start_direct)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.GET, self._handler_command_get)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.SET, self._handler_command_set)

        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.ENTER, self._handler_direct_access_enter)
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.EXIT, self._handler_direct_access_exit)
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.STOP_DIRECT, self._handler_direct_access_stop_direct)
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.EXECUTE_DIRECT, self._handler_direct_access_execute_direct)

        # Construct the parameter dictionary containing device parameters,
        # current parameter values, and set formatting functions.
        self._build_param_dict()

        # Add build handlers for device commands.

        # Add response handlers for device commands.

        # Add sample handlers.

        # State state machine in UNKNOWN state.
        self._protocol_fsm.start(ProtocolState.UNKNOWN)

        # commands sent sent to device to be filtered in responses for telnet DA
        self._sent_cmds = []

        #
        self._chunker = StringChunker(Protocol.sieve_function)


    @staticmethod
    def sieve_function(raw_data):
        """
        The method that splits samples
        Chunker sieve method to help the chunker identify chunks.
        @returns a list of chunks identified, if any. The chunks are all the same type.
        """
        sieve_matchers = [CZ_REGEX_MATCHER,
#                          BREAK_REGEX_MATCHER,
                          ERR_REGEX_MATCHER]

        return_list = []

        for matcher in sieve_matchers:
            for match in matcher.finditer(raw_data):
                return_list.append((match.start(), match.end()))

        return return_list


    def _build_param_dict(self):
        """
        Populate the parameter dictionary with parameters.
        For each parameter key, add match stirng, match lambda function,
        and value formatting function for set commands.
        """
        # Add parameter handlers to parameter dict.

    def _got_chunk(self, chunk):
        """
        The base class got_data has gotten a chunk from the chunker.  Pass it to extract_sample
        with the appropriate particle objects and REGEXes.
        """

    def _filter_capabilities(self, events):
        """
        Return a list of currently available capabilities.
        """
        return [x for x in events if Capability.has(x)]

    ########################################################################
    # Unknown handlers.
    ########################################################################

    def _handler_unknown_enter(self, *args, **kwargs):
        """
        Enter unknown state.
        """
        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)

    def _handler_unknown_exit(self, *args, **kwargs):
        """
        Exit unknown state.
        """
        pass

    def _handler_unknown_discover(self, *args, **kwargs):
        """
        Discover current state
        @retval (next_state, result)
        """
        return (ProtocolState.COMMAND, ResourceAgentState.IDLE)

    ########################################################################
    # Command handlers.
    ########################################################################

    def _handler_command_enter(self, *args, **kwargs):
        """
        Enter command state.
        @throws InstrumentTimeoutException if the device cannot be woken.
        @throws InstrumentProtocolException if the update commands and not recognized.
        """
        # Command device to update parameters and send a config change event.
        #self._update_params()

        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)

    def _handler_command_get(self, *args, **kwargs):
        """
        Get parameter
        """
        next_state = None
        result = None


        return (next_state, result)

    def _handler_command_set(self, *args, **kwargs):
        """
        Set parameter
        """
        next_state = None
        result = None

        return (next_state, result)

    def _handler_command_exit(self, *args, **kwargs):
        """
        Exit command state.
        """
        pass

    def _handler_command_start_direct(self):
        """
        Start direct access
        """
        next_state = ProtocolState.DIRECT_ACCESS
        next_agent_state = ResourceAgentState.DIRECT_ACCESS
        result = None
        log.debug("_handler_command_start_direct: entering DA mode")
        return (next_state, (next_agent_state, result))

    ########################################################################
    # Direct access handlers.
    ########################################################################

    def _handler_direct_access_enter(self, *args, **kwargs):
        """
        Enter direct access state.
        """
        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)

        self._sent_cmds = []

    def _handler_direct_access_exit(self, *args, **kwargs):
        """
        Exit direct access state.
        """
        pass

    def _handler_direct_access_execute_direct(self, data):
        """
        """
        next_state = None
        result = None
        next_agent_state = None

        self._do_cmd_direct(data)

        # add sent command to list for 'echo' filtering in callback
        self._sent_cmds.append(data)

        return (next_state, (next_agent_state, result))

    def _handler_direct_access_stop_direct(self):
        """
        @throw InstrumentProtocolException on invalid command
        """
        next_state = None
        result = None

        next_state = ProtocolState.COMMAND
        next_agent_state = ResourceAgentState.COMMAND

        return (next_state, (next_agent_state, result))

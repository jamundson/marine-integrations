"""
@package mi.instrument.satlantic.suna_deep.ooicore.driver
@file marine-integrations/mi/instrument/satlantic/suna_deep/ooicore/driver.py
@author Anton Kueltz
@brief Driver for the ooicore
Release notes:

initial_rev
"""

__author__ = 'Anton Kueltz'
__license__ = 'Apache 2.0'

from mi.core.log import get_logger, get_logging_metaclass
log = get_logger()

import re
import json
import pprint

from mi.core.common import BaseEnum, Units
from mi.core.common import InstErrorCode

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
from mi.core.instrument.protocol_param_dict import ParameterDictVisibility
from mi.core.instrument.protocol_param_dict import ParameterDictType

from mi.core.exceptions import SampleException
from mi.core.exceptions import InstrumentProtocolException
from mi.core.exceptions import InstrumentParameterException
from mi.core.exceptions import InstrumentException


# newline.
NEWLINE = '\r\n'

# default timeout.
TIMEOUT = 15

# default number of retries for a command
RETRY = 3

# SUNA ASCII FRAME REGEX
SUNA_SAMPLE_PATTERN = r'SAT'                # Sentinal
SUNA_SAMPLE_PATTERN += r'([A-Z]{3})'        # 1: Frame Type (string)
SUNA_SAMPLE_PATTERN += r'(\d{4}),'          # 2: Serial Number (int)
SUNA_SAMPLE_PATTERN += r'(\d{7}),'          # 3: Date, year and day-of-year (int)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 4. Time, hours of day (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 5. Nitrate concentration [uM] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 6. Nitrogen in nitrate [mg/l] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 7. Absorbance at 254 nm (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 8. Absorbance at 350 nm (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 9. Bromide trace [mg/l] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*),'       # 10. Spectrum average (int)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*),'       # 11. Dark value used for fit (int)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*),'       # 12. Integration time factor (int)
SUNA_SAMPLE_PATTERN += r'('                 # 13. Spectrum channels (open group)
for i in range(255):
    SUNA_SAMPLE_PATTERN += r'[+-]?\d*,'     # 13. Spectrum channels (255 x int)
SUNA_SAMPLE_PATTERN += r'[+-]?\d*),'        # 13. Spectrum channels (close group, last int = 256th)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 14. Internal temperature [C] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 15. Spectrometer temperature [C] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 16. Lamp temperature [C] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*),'       # 17. Cumulative lamp on-time [s] (int)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 18. Relative Humidity [%] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 19. Main Voltage [V] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 20. Lamp Voltage [V] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 21. Internal Voltage [V] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 22. Main Current [mA] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 23. Fit Aux 1 (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 24. Fit Aux 2 (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 25. Fit Base 1 (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 26. Fit Base 2 (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*.\d*),'   # 27. Fit RMSE (float)
SUNA_SAMPLE_PATTERN += r','  # r'([+-]?\d*),'       # 28. CTD Time [seconds since 1970] (int)
SUNA_SAMPLE_PATTERN += r','  # r'([+-]?\d*.\d*),'   # 29. CTD Salinity [PSU] (float)
SUNA_SAMPLE_PATTERN += r','  # r'([+-]?\d*.\d*),'   # 30. CTD Temperature [C] (float)
SUNA_SAMPLE_PATTERN += r','  # r'([+-]?\d*.\d*),'   # 31. CTD Pressure [dBar] (float)
SUNA_SAMPLE_PATTERN += r'([+-]?\d*)'        # 32. Check Sum (int)
SUNA_SAMPLE_PATTERN += r'\r\n'              # <Carriage Return> <Line Feed>

SUNA_SAMPLE_REGEX = re.compile(SUNA_SAMPLE_PATTERN)

# SUNA STATUS REGEX
SUNA_STATUS_PATTERN = r'SENSTYPE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SENSVERS\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SERIALNO\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'INTWIPER\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'EXTPPORT\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'LMPSHUTR\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'REFDTECT\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'PROTECTR\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SUPRCAPS\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'PWRSVISR\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'USBSWTCH\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'RELAYBRD\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SDI12BRD\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'ANALGBRD\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'INTDATLG\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'APFIFACE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SCHDLING\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'FANATLMP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'OWIRETLP\s+([0-9a-f]+)\s+'
SUNA_STATUS_PATTERN += r'OWIRETSP\s+([0-9a-f]+)\s+'
SUNA_STATUS_PATTERN += r'OWIRETHS\s+([0-9a-f]+)\s+'
SUNA_STATUS_PATTERN += r'ZSPEC_SN\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'FIBERLSN\s+([\w.]+)\s+'
SUNA_STATUS_PATTERN += r'STUPSTUS\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'BRNHOURS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'BRNNUMBR\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKHOURS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKNUMBR\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'CHRLDURA\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'CHRDDURA\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'BAUDRATE\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'MSGLEVEL\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'MSGFSIZE\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DATFSIZE\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'OUTFRTYP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'LOGFRTYP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'OUTDRKFR\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'LOGDRKFR\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'TIMERESL\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'LOGFTYPE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'ACQCOUNT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'CNTCOUNT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DCMINNO3\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'DCMAXNO3\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'WDAT_LOW\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'WDAT_HGH\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'SDI12ADD\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DATAMODE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'OPERMODE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'OPERCTRL\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'EXDEVTYP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'EXDEVPRE\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'EXDEVRUN\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'WATCHDOG\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'COUNTDWN\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'FIXDDURA\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'PERDIVAL\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'PERDOFFS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'PERDDURA\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'PERDSMPL\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'POLLTOUT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'APFATOFF\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'STBLTIME\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'REFLIMIT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'SKPSLEEP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'LAMPTOFF\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'SPINTPER\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKAVERS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'LGTAVERS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'REFSMPLS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKSMPLS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'LGTSMPLS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKDURAT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'LGTDURAT\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'TEMPCOMP\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'SALINFIT\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'BRMTRACE\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'BL_ORDER\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'FITCONCS\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'DRKCORMT\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'DRKCOEFS\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'DAVGPRM0\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'DAVGPRM1\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'DAVGPRM2\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'DAVGPRM3\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'A_CUTOFF\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'INTPRADJ\s+(\w+)\s+'
SUNA_STATUS_PATTERN += r'INTPRFAC\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'INTADSTP\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'INTADMAX\s+(\d+)\s+'
SUNA_STATUS_PATTERN += r'WFIT_LOW\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'WFIT_HGH\s+([+-]?\d+.\d+)\s+'
SUNA_STATUS_PATTERN += r'LAMPTIME\s+(\d+)\s+'

SUNA_STATUS_REGEX = re.compile(SUNA_STATUS_PATTERN)

# SUNA TEST REGEX
SUNA_TEST_PATTERN = r'Extrn Disk Size; Free , (\d+); (\d+)\s+'
SUNA_TEST_PATTERN += r'Intrn Disk Size; Free , (\d+); (\d+)\s+'
SUNA_TEST_PATTERN += r'Fiberlite\s+Odometer , (\d+:\d+:\d+)\s+'
SUNA_TEST_PATTERN += r'Temperatures Hs Sp Lm , ([+-]?\d+.\d+) ([+-]?\d+.\d+) ([+-]?\d+.\d+)\s+'
SUNA_TEST_PATTERN += r'Humidity\s+, ([+-]?\d+.\d+)\s+'
SUNA_TEST_PATTERN += r'Electrical Mn Bd Pr C , ([+-]?\d+.\d+) ([+-]?\d+.\d+) ([+-]?\d+.\d+) ([+-]?\d+.\d+)\s+'
SUNA_TEST_PATTERN += r'Lamp\s+Power , (\d+) mW\s+'
SUNA_TEST_PATTERN += r'Spec Dark av sd mi ma ,\s+(\d+) \(\+/-\s+(\d+)\) \[\s*(\d+):\s*(\d+)\]\s+'
SUNA_TEST_PATTERN += r'Spec Lght av sd mi ma ,\s+(\d+) \(\+/-\s+(\d+)\) \[\s*(\d+):\s*(\d+)\]\s+'
SUNA_TEST_PATTERN += r'\$(Ok|Error)'

SUNA_TEST_REGEX = re.compile(SUNA_TEST_PATTERN)


###
#    Driver Constant Definitions
###
class ParameterUnit(BaseEnum):
    DECISIEMENS = 'dS'
    MEGABYTE = 'MB'


class DataParticleType(BaseEnum):
    """
    Data particle types produced by this driver
    """
    RAW = CommonDataParticleType.RAW
    SUNA_SAMPLE = "suna_sample"
    SUNA_STATUS = "suna_status"
    SUNA_TEST = "suna_test"


class ProtocolState(BaseEnum):
    """
    Instrument protocol states
    """
    UNKNOWN = DriverProtocolState.UNKNOWN
    COMMAND = DriverProtocolState.COMMAND
    DIRECT_ACCESS = DriverProtocolState.DIRECT_ACCESS
    POLL = DriverProtocolState.POLL
    AUTOSAMPLE = DriverProtocolState.AUTOSAMPLE


class ProtocolEvent(BaseEnum):
    """
    Protocol events
    """
    DISCOVER = DriverEvent.DISCOVER
    INITIALIZE = DriverEvent.INITIALIZE
    ACQUIRE_SAMPLE = DriverEvent.ACQUIRE_SAMPLE
    START_AUTOSAMPLE = DriverEvent.START_AUTOSAMPLE
    STOP_AUTOSAMPLE = DriverEvent.STOP_AUTOSAMPLE
    TEST = DriverEvent.TEST
    START_DIRECT = DriverEvent.START_DIRECT
    STOP_DIRECT = DriverEvent.STOP_DIRECT
    CLOCK_SYNC = DriverEvent.CLOCK_SYNC
    ACQUIRE_STATUS = DriverEvent.ACQUIRE_STATUS
    RESET = DriverEvent.RESET

    START_POLL = "DRIVER_EVENT_START_POLL"
    STOP_POLL = "DRIVER_EVENT_STOP_POLL"
    MEASURE_N = "DRIVER_EVENT_MEASURE_N"
    MEASURE_0 = "DRIVER_EVENT_MEASURE_0"
    TIMED_N = "DRIVER_EVENT_TIMED_N"

    GET = DriverEvent.GET
    SET = DriverEvent.SET
    EXECUTE_DIRECT = DriverEvent.EXECUTE_DIRECT
    ENTER = DriverEvent.ENTER
    EXIT = DriverEvent.EXIT


class Capability(BaseEnum):
    """
    Protocol events that should be exposed to users (subset of above).
    """
    # Get Sample & Status Data
    ACQUIRE_SAMPLE = ProtocolEvent.ACQUIRE_SAMPLE
    ACQUIRE_STATUS = ProtocolEvent.ACQUIRE_STATUS
    MEASURE_N = ProtocolEvent.MEASURE_N
    MEASURE_0 = ProtocolEvent.MEASURE_0
    TIMED_N = ProtocolEvent.TIMED_N
    TEST = ProtocolEvent.TEST

    # Change States
    START_AUTOSAMPLE = ProtocolEvent.START_AUTOSAMPLE
    STOP_AUTOSAMPLE = ProtocolEvent.STOP_AUTOSAMPLE
    START_POLL = ProtocolEvent.START_POLL
    STOP_POLL = ProtocolEvent.STOP_POLL

    # Parameter Accessors/Mutators
    GET = ProtocolEvent.GET
    SET = ProtocolEvent.SET


class Parameter(DriverParameter):
    #Data Acquisition
    OPERATION_MODE = "opermode"
    OPERATION_CONTROL = "operctrl"
    LIGHT_SAMPLES = "lgtsmpls"
    DARK_SAMPLES = "drksmpls"
    LIGHT_DURATION = "lgtdurat"
    DARK_DURATION = "drkdurat"
    COUNTDOWN = "countdwn"

    #Data Processing
    TEMP_COMPENSATION = "tempcomp"
    FIT_WAVELENGTH_LOW = "wfit_low"     # read/get only
    FIT_WAVELENGTH_HIGH = "wfit_hgh"    # read/get only
    FIT_WAVELENGTH_BOTH = "wfitboth"    # set only
    CONCENTRATIONS_IN_FIT = "fitconcs"
    BASELINE_ORDER = "bl_order"
    DARK_CORRECTION_METHOD = "drkcormt"
    SALINITY_FITTING = "salinfit"
    BROMIDE_TRACING = "brmtrace"
    ABSORBANCE_CUTOFF = "a_cutoff"
    INTEG_TIME_ADJUSTMENT = "intpradj"
    INTEG_TIME_FACTOR = "intprfac"
    INTEG_TIME_STEP = "intadstp"
    INTEG_TIME_MAX = "intadmax"

    #Driver Parameters
    NUM_LIGHT_SAMPLES = "nmlgtspl"
    TIME_LIGHT_SAMPLE = "tlgtsmpl"

    #Data Acquisition
    REF_MIN_AT_LAMP_ON = "reflimit"  # read only
    SPECTROMETER_INTEG_PERIOD = "spintper"  # read only

    #Data Acquisition
    POLLED_TIMEOUT = "polltout"  # startup
    SKIP_SLEEP_AT_START = "skpsleep"  # startup
    LAMP_STABIL_TIME = "stbltime"  # startup
    LAMP_SWITCH_OFF_TEMPERATURE = "lamptoff"  # startup

    #I/O
    MESSAGE_LEVEL = "msglevel"  # startup
    MESSAGE_FILE_SIZE = "msgfsize"  # startup
    DATA_FILE_SIZE = "datfsize"  # startup
    OUTPUT_FRAME_TYPE = "outfrtyp"  # startup
    OUTPUT_DARK_FRAME = "outdrkfr"  # startup

PARAM_TYPE_FUNC = {Parameter.OPERATION_MODE: str, Parameter.OPERATION_CONTROL: str, Parameter.LIGHT_SAMPLES: int,
                   Parameter.DARK_SAMPLES: int, Parameter.LIGHT_DURATION: int, Parameter.DARK_DURATION: int,
                   Parameter.COUNTDOWN: int, Parameter.TEMP_COMPENSATION: str, Parameter.FIT_WAVELENGTH_LOW: float,
                   Parameter.FIT_WAVELENGTH_HIGH: float, Parameter.CONCENTRATIONS_IN_FIT: int,
                   Parameter.BASELINE_ORDER: int, Parameter.DARK_CORRECTION_METHOD: str,
                   Parameter.SALINITY_FITTING: str, Parameter.BROMIDE_TRACING: str,
                   Parameter.ABSORBANCE_CUTOFF: float, Parameter.INTEG_TIME_ADJUSTMENT: str,
                   Parameter.INTEG_TIME_FACTOR: int, Parameter.INTEG_TIME_STEP: int, Parameter.INTEG_TIME_MAX: int,
                   Parameter.REF_MIN_AT_LAMP_ON: int, Parameter.SPECTROMETER_INTEG_PERIOD: int,
                   Parameter.POLLED_TIMEOUT: int, Parameter.SKIP_SLEEP_AT_START: str,
                   Parameter.LAMP_STABIL_TIME: int, Parameter.LAMP_SWITCH_OFF_TEMPERATURE: int,
                   Parameter.MESSAGE_LEVEL: str, Parameter.MESSAGE_FILE_SIZE: int, Parameter.DATA_FILE_SIZE: int,
                   Parameter.OUTPUT_FRAME_TYPE: str, Parameter.OUTPUT_DARK_FRAME: str}


class Prompt(BaseEnum):
    """
    Device i/o prompts..
    """
    COMMAND = "SUNA>"
    POLLED = "CMD?"

    SET_OK = r'.*\r\n(\$Ok)\s+'
    OK = r'.*\r\n\$Ok ([\w.]+)\s+'
    ERROR = r'.*\r\n\$Error: (\d+)\s+'
    WAKEUP = "Charging power loss protector."

    SAMPLING = 'SAT'


class InstrumentCommand(BaseEnum):
    """
    Instrument command strings
    """
    #Status and Maintenance
    CMD_LINE = "$"
    GET_CLOCK = "get clock"
    SET_CLOCK = "set clock"
    UPGRADE = "upgrade"
    REBOOT = "reboot"
    EXIT = "exit"
    GET_LAMPTIME = "get lamptime"
    GET_ACTIVECALFILE = "get activecalfile"
    SELFTEST = "selftest"
    STATUS = "get cfg"

    #File Commands
    LIST = "List"
    OUTPUT = "Output"
    SEND = "Send"
    DELETE = "Delete"
    RECEIVE = "Receive"

    # Polled Mode
    START = "Start"
    MEASURE = "Measure"     # takes param n indicating amount of light frames
    TIMED = "Timed"         # takes param n indicating duration in seconds to take light frames for
    CTD = "CTD"
    SLEEP = "Sleep"

    # Command Line Commands
    GET = "get"         # takes param that indicates which field to get
    SET = "set"         # takes params that indicate which field to set and what value to set it to


class InstrumentCommandArgs(BaseEnum):
    POLLED = 'Polled'
    CONTINUOUS = 'Continuous'


class LastSampleState(BaseEnum):
    POLL = "poll"
    AUTO = "auto"


class SUNASampleDataParticleKey(BaseEnum):
    FRAME_TYPE = "frame_type"
    SERIAL_NUM = "serial_number"
    SAMPLE_DATE = "date_of_sample"
    SAMPLE_TIME = "time_of_sample"
    NITRATE_CONCEN = "nitrate_concentration"
    NITROGEN = "nutnr_nitrogen_in_nitrate"
    ABSORB_254 = "nutnr_absorbance_at_254_nm"
    ABSORB_350 = "nutnr_absorbance_at_350_nm"
    BROMIDE_TRACE = "nutnr_bromide_trace"
    SPECTRUM_AVE = "nutnr_spectrum_average"
    FIT_DARK_VALUE = "nutnr_dark_value_used_for_fit"
    TIME_FACTOR = "nutnr_integration_time_factor"
    SPECTRAL_CHANNELS = "spectral_channels"
    TEMP_SPECTROMETER = "temp_spectrometer"
    TEMP_INTERIOR = "temp_interior"
    TEMP_LAMP = "temp_lamp"
    LAMP_TIME = "lamp_time"
    HUMIDITY = "humidity"
    VOLTAGE_MAIN = "voltage_main"
    VOLTAGE_LAMP = "voltage_lamp"
    VOLTAGE_INT = "nutnr_voltage_int"
    CURRENT_MAIN = "nutnr_current_main"
    FIT_1 = "aux_fitting_1"
    FIT_2 = "aux_fitting_2"
    FIT_BASE_1 = "nutnr_fit_base_1"
    FIT_BASE_2 = "nutnr_fit_base_2"
    FIT_RMSE = "nutnr_fit_rmse"
    CHECKSUM = "checksum"


###############################################################################
# Data Particles
###############################################################################
class SUNASampleDataParticle(DataParticle):
    _data_particle_type = DataParticleType.SUNA_SAMPLE

    def _build_parsed_values(self):
        matched = SUNA_SAMPLE_REGEX.match(self.raw_data)

        if not matched:
            raise SampleException("No regex match for sample [%s]" %
                                  self.raw_data)
        try:
            parsed_data_list = [
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FRAME_TYPE, DataParticleKey.VALUE: str(matched.group(1))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.SERIAL_NUM, DataParticleKey.VALUE: str(matched.group(2))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.SAMPLE_DATE, DataParticleKey.VALUE: int(matched.group(3))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.SAMPLE_TIME, DataParticleKey.VALUE: float(matched.group(4))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.NITRATE_CONCEN, DataParticleKey.VALUE: float(matched.group(5))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.NITROGEN, DataParticleKey.VALUE: float(matched.group(6))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.ABSORB_254, DataParticleKey.VALUE: float(matched.group(7))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.ABSORB_350, DataParticleKey.VALUE: float(matched.group(8))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.BROMIDE_TRACE, DataParticleKey.VALUE: float(matched.group(9))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.SPECTRUM_AVE, DataParticleKey.VALUE: int(matched.group(10))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_DARK_VALUE, DataParticleKey.VALUE: int(matched.group(11))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.TIME_FACTOR, DataParticleKey.VALUE: int(matched.group(12))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.SPECTRAL_CHANNELS, DataParticleKey.VALUE: [int(s) for s in matched.group(13).split(',')]},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.TEMP_SPECTROMETER, DataParticleKey.VALUE: float(matched.group(14))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.TEMP_INTERIOR, DataParticleKey.VALUE: float(matched.group(15))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.TEMP_LAMP, DataParticleKey.VALUE: float(matched.group(16))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.LAMP_TIME, DataParticleKey.VALUE: int(matched.group(17))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.HUMIDITY, DataParticleKey.VALUE: float(matched.group(18))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.VOLTAGE_MAIN, DataParticleKey.VALUE: float(matched.group(19))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.VOLTAGE_LAMP, DataParticleKey.VALUE: float(matched.group(20))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.VOLTAGE_INT, DataParticleKey.VALUE: float(matched.group(21))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.CURRENT_MAIN, DataParticleKey.VALUE: float(matched.group(22))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_1, DataParticleKey.VALUE: float(matched.group(23))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_2, DataParticleKey.VALUE: float(matched.group(24))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_BASE_1, DataParticleKey.VALUE: float(matched.group(25))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_BASE_2, DataParticleKey.VALUE: float(matched.group(26))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.FIT_RMSE, DataParticleKey.VALUE: float(matched.group(27))},
                {DataParticleKey.VALUE_ID: SUNASampleDataParticleKey.CHECKSUM, DataParticleKey.VALUE: int(matched.group(28))}]

        except ValueError:
            raise SampleException("ValueError while parsing data [%s]" %
                                  self.raw_data)

        return parsed_data_list


class SUNAStatusDataParticleKey(BaseEnum):
    SENSOR_TYPE = "nutnr_sensor_type"
    SENSOR_VERSION = "nutnr_sensor_version"
    SERIAL_NUMBER = "serial_number"
    INTEGRATED_WIPER = "nutnr_integrated_wiper"
    EXT_POWER_PORT = "nutnr_ext_power_port"
    LAMP_SHUTTER = "nutnr_lamp_shutter"
    REF_DETECTOR = "nutnr_reference_detector"
    PROTECTR = "protectr",
    SUPER_CAPACITORS = "nutnr_super_capacitors"
    PSB_SUPERVISOR = "nutnr_psb_supervisor"
    USB_COMM = "nutnr_usb_communication"
    RELAY_MODULE = "nutnr_relay_module"
    SDII2_INTERFACE = "nutnr_sdi12_interface"
    ANALOG_OUTPUT = "nutnr_analog_output"
    DATA_LOGGING = "nutnr_int_data_logging"
    APF_INTERFACE = "nutnr_apf_interface"
    SCHEDULING = "nutnr_scheduling"
    LAMP_FAN = "nutnr_lamp_fan"
    ADDR_LAMP_TEMP = "nutnr_sensor_address_lamp_temp"
    ADDR_SPEC_TEMP = "nutnr_sensor_address_spec_temp"
    SENSOR_ADDR_HOUS_TEMP = "nutnr_sensor_address_hous_temp"
    SERIAL_NUM_SPECT = "nutnr_serial_number_spec"
    SERIAL_NUM_LAMP = "nutnr_serial_number_lamp"
    STUPSTUS = "stupstus",
    BRNHOURS = "brnhours"
    BRNNUMBER = "brnnumbr"
    DARK_HOURS = "drkhours"
    DARK_NUM = "drknumbr"
    CHRLDURA = "chrldura"
    CHRDDURA = "chrddura"
    BAUD_RATE = "baud_rate"
    MSG_LEVEL = "nutnr_msg_level"
    MSG_FILE_SIZE = "nutnr_msg_file_size"
    DATA_FILE_SIZE = "nutnr_data_file_size"
    OUTPUT_FRAME_TYPE = "nutnr_output_frame_type"
    LOGGING_FRAME_TYPE = "nutnr_logging_frame_type"
    OUTPUT_DARK_FRAME = "nutnr_output_dark_frame"
    LOGGING_DARK_FRAME = "nutnr_logging_dark_frame"
    TIMERESL = "timeresl"
    LOG_FILE_TYPE = "nutnr_log_file_type"
    ACQCOUNT = "acqcount",
    CNTCOUNT = "cntcount",
    NITRATE_MIN = "nutnr_dac_nitrate_min"
    NITRATE_MAX = "nutnr_dac_nitrate_max"
    WAVELENGTH_LOW = "nutnr_data_wavelength_low"
    WAVELENGTH_HIGH = "nutnr_data_wavelength_high"
    SDI12_ADDR = "nutnr_sdi12_address"
    DATAMODE = "datamode"
    OPERATING_MODE = "operating_mode"
    OPERATION_CTRL = "nutnr_operation_ctrl"
    EXTL_DEV = "nutnr_extl_dev"
    PRERUN_TIME = "nutnr_ext_dev_prerun_time"
    DEV_DURING_ACQ = "nutnr_ext_dev_during_acq"
    WATCHDOG_TIME = "nutnr_watchdog_timer"
    COUNTDOWN = "nutnr_countdown"
    FIXED_TIME = "nutnr_fixed_time_duration"
    PERIODIC_INTERVAL = "nutnr_periodic_interval"
    PERIODIC_OFFSET = "nutnr_periodic_offset"
    PERIODIC_DURATION = "nutnr_periodic_duration"
    PERIODIC_SAMPLES = "nutnr_periodic_samples"
    POLLED_TIMEOUT = "nutnr_polled_timeout"
    APF_TIMEOUT = "nutnr_apf_timeout"
    STABILITY_TIME = "nutnr_stability_time"
    MIN_LAMP_ON = "nutnr_ref_min_lamp_on"
    SKIP_SLEEP = "nutnr_skip_sleep"
    SWITCHOFF_TEMP = "nutnr_lamp_switchoff_temp"
    SPEC_PERIOD = "nutnr_spec_integration_period"
    DRKAVERS = "drkavers"
    LGTAVERS = "lgtavers"
    REFSAMPLES = "refsmpls"
    DARK_SAMPLES = "nutnr_dark_samples",
    LIGHT_SAMPLES = "nutnr_light_samples"
    DARK_DURATION = "nutnr_dark_duration"
    LIGHT_DURATION = "nutnr_light_duration"
    TEMP_COMP = "nutnr_temp_comp",
    SALINITY_FIT = "nutnr_salinity_fit"
    BROMIDE_TRACING = "nutnr_bromide_tracing"
    BASELINE_ORDER = "nutnr_baseline_order"
    CONCENTRATIONS_FIT = "nutnr_concentrations_fit"
    DARK_CORR_METHOD = "nutnr_dark_corr_method"
    DRKCOEFS = "drkcoefs"
    DAVGPRM_0 = "davgprm0"
    DAVGPRM_1 = "davgprm1"
    DAVGPRM_2 = "davgprm2"
    DAVGPRM_3 = "davgprm3"
    ABSORBANCE_CUTOFF = "nutnr_absorbance_cutoff"
    TIME_ADJ = "nutnr_int_time_adj"
    TIME_FACTOR = "nutnr_int_time_factor"
    TIME_STEP = "nutnr_int_time_step"
    TIME_MAX = "nutnr_int_time_max"
    FIT_WAVE_LOW = "nutnr_fit_wavelength_low"
    FIT_WAVE_HIGH = "nutnr_fit_wavelength_high"
    LAMP_TIME = "lamp_time"


class SUNAStatusDataParticle(DataParticle):
    _data_particle_type = DataParticleType.SUNA_STATUS

    def _build_parsed_values(self):
        matched = SUNA_STATUS_REGEX.match(self.raw_data)

        if not matched:
            raise SampleException("No regex match for status [%s]" % self.raw_data)
        try:
            parsed_data_list = [
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SENSOR_TYPE, DataParticleKey.VALUE: str(matched.group(1))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SENSOR_VERSION, DataParticleKey.VALUE: str(matched.group(2))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SERIAL_NUMBER, DataParticleKey.VALUE: int(matched.group(3))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.INTEGRATED_WIPER, DataParticleKey.VALUE: str(matched.group(4))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.EXT_POWER_PORT, DataParticleKey.VALUE: str(matched.group(5))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LAMP_SHUTTER, DataParticleKey.VALUE: str(matched.group(6))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.REF_DETECTOR, DataParticleKey.VALUE: str(matched.group(7))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PROTECTR, DataParticleKey.VALUE: str(matched.group(8))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SUPER_CAPACITORS, DataParticleKey.VALUE: str(matched.group(9))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PSB_SUPERVISOR, DataParticleKey.VALUE: str(matched.group(10))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.USB_COMM, DataParticleKey.VALUE: str(matched.group(11))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.RELAY_MODULE, DataParticleKey.VALUE: str(matched.group(12))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SDII2_INTERFACE, DataParticleKey.VALUE: str(matched.group(13))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.ANALOG_OUTPUT, DataParticleKey.VALUE: str(matched.group(14))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DATA_LOGGING, DataParticleKey.VALUE: str(matched.group(15))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.APF_INTERFACE, DataParticleKey.VALUE: str(matched.group(16))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SCHEDULING, DataParticleKey.VALUE: str(matched.group(17))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LAMP_FAN, DataParticleKey.VALUE: str(matched.group(18))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.ADDR_LAMP_TEMP, DataParticleKey.VALUE: str(matched.group(19))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.ADDR_SPEC_TEMP, DataParticleKey.VALUE: str(matched.group(20))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SENSOR_ADDR_HOUS_TEMP, DataParticleKey.VALUE: str(matched.group(21))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SERIAL_NUM_SPECT, DataParticleKey.VALUE: int(matched.group(22))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SERIAL_NUM_LAMP, DataParticleKey.VALUE: str(matched.group(23))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.STUPSTUS, DataParticleKey.VALUE: str(matched.group(24))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.BRNHOURS, DataParticleKey.VALUE: int(matched.group(25))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.BRNNUMBER, DataParticleKey.VALUE: int(matched.group(26))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DARK_HOURS, DataParticleKey.VALUE: int(matched.group(27))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DARK_NUM, DataParticleKey.VALUE: int(matched.group(28))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.CHRLDURA, DataParticleKey.VALUE: int(matched.group(29))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.CHRDDURA, DataParticleKey.VALUE: int(matched.group(30))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.BAUD_RATE, DataParticleKey.VALUE: int(matched.group(31))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.MSG_LEVEL, DataParticleKey.VALUE: str(matched.group(32))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.MSG_FILE_SIZE, DataParticleKey.VALUE: int(matched.group(33))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DATA_FILE_SIZE, DataParticleKey.VALUE: int(matched.group(34))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.OUTPUT_FRAME_TYPE, DataParticleKey.VALUE: str(matched.group(35))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LOGGING_FRAME_TYPE, DataParticleKey.VALUE: str(matched.group(36))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.OUTPUT_DARK_FRAME, DataParticleKey.VALUE: str(matched.group(37))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LOGGING_DARK_FRAME, DataParticleKey.VALUE: str(matched.group(38))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TIMERESL, DataParticleKey.VALUE: str(matched.group(39))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LOG_FILE_TYPE, DataParticleKey.VALUE: str(matched.group(40))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.ACQCOUNT, DataParticleKey.VALUE: int(matched.group(41))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.CNTCOUNT, DataParticleKey.VALUE: int(matched.group(42))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.NITRATE_MIN, DataParticleKey.VALUE: float(matched.group(43))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.NITRATE_MAX, DataParticleKey.VALUE: float(matched.group(44))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.WAVELENGTH_LOW, DataParticleKey.VALUE: float(matched.group(45))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.WAVELENGTH_HIGH, DataParticleKey.VALUE: float(matched.group(46))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SDI12_ADDR, DataParticleKey.VALUE: int(matched.group(47))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DATAMODE, DataParticleKey.VALUE: str(matched.group(48))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.OPERATING_MODE, DataParticleKey.VALUE: str(matched.group(49))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.OPERATION_CTRL, DataParticleKey.VALUE: str(matched.group(50))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.EXTL_DEV, DataParticleKey.VALUE: str(matched.group(51))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PRERUN_TIME, DataParticleKey.VALUE: int(matched.group(52))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DEV_DURING_ACQ, DataParticleKey.VALUE: str(matched.group(53))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.WATCHDOG_TIME, DataParticleKey.VALUE: str(matched.group(54))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.COUNTDOWN, DataParticleKey.VALUE: int(matched.group(55))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.FIXED_TIME, DataParticleKey.VALUE: int(matched.group(56))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PERIODIC_INTERVAL, DataParticleKey.VALUE: str(matched.group(57))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PERIODIC_OFFSET, DataParticleKey.VALUE: int(matched.group(58))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PERIODIC_DURATION, DataParticleKey.VALUE: int(matched.group(59))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.PERIODIC_SAMPLES, DataParticleKey.VALUE: int(matched.group(60))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.POLLED_TIMEOUT, DataParticleKey.VALUE: int(matched.group(61))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.APF_TIMEOUT, DataParticleKey.VALUE: float(matched.group(62))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.STABILITY_TIME, DataParticleKey.VALUE: int(matched.group(63))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.MIN_LAMP_ON, DataParticleKey.VALUE: int(matched.group(64))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SKIP_SLEEP, DataParticleKey.VALUE: str(matched.group(65))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SWITCHOFF_TEMP, DataParticleKey.VALUE: int(matched.group(66))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SPEC_PERIOD, DataParticleKey.VALUE: int(matched.group(67))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DRKAVERS, DataParticleKey.VALUE: int(matched.group(68))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LGTAVERS, DataParticleKey.VALUE: int(matched.group(69))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.REFSAMPLES, DataParticleKey.VALUE: int(matched.group(70))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DARK_SAMPLES, DataParticleKey.VALUE: int(matched.group(71))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LIGHT_SAMPLES, DataParticleKey.VALUE: int(matched.group(72))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DARK_DURATION, DataParticleKey.VALUE: int(matched.group(73))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LIGHT_DURATION, DataParticleKey.VALUE: int(matched.group(74))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TEMP_COMP, DataParticleKey.VALUE: str(matched.group(75))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.SALINITY_FIT, DataParticleKey.VALUE: str(matched.group(76))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.BROMIDE_TRACING, DataParticleKey.VALUE: str(matched.group(77))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.BASELINE_ORDER, DataParticleKey.VALUE: int(matched.group(78))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.CONCENTRATIONS_FIT, DataParticleKey.VALUE: int(matched.group(79))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DARK_CORR_METHOD, DataParticleKey.VALUE: str(matched.group(80))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DRKCOEFS, DataParticleKey.VALUE: str(matched.group(81))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DAVGPRM_0, DataParticleKey.VALUE: float(matched.group(82))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DAVGPRM_1, DataParticleKey.VALUE: float(matched.group(83))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DAVGPRM_2, DataParticleKey.VALUE: float(matched.group(84))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.DAVGPRM_3, DataParticleKey.VALUE: float(matched.group(85))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.ABSORBANCE_CUTOFF, DataParticleKey.VALUE: float(matched.group(86))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TIME_ADJ, DataParticleKey.VALUE: str(matched.group(87))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TIME_FACTOR, DataParticleKey.VALUE: int(matched.group(88))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TIME_STEP, DataParticleKey.VALUE: int(matched.group(89))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.TIME_MAX, DataParticleKey.VALUE: int(matched.group(90))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.FIT_WAVE_LOW, DataParticleKey.VALUE: float(matched.group(91))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.FIT_WAVE_HIGH, DataParticleKey.VALUE: float(matched.group(92))},
                {DataParticleKey.VALUE_ID: SUNAStatusDataParticleKey.LAMP_TIME, DataParticleKey.VALUE: int(matched.group(93))}]

        except ValueError:
            raise SampleException("ValueError while parsing data [%s]" % self.raw_data)

        return parsed_data_list


class SUNATestDataParticleKey(BaseEnum):
    EXT_DISK_SIZE = "nutnr_external_disk_size"
    EXT_DISK_FREE = "nutnr_external_disk_free"
    INT_DISK_SIZE = "nutnr_internal_disk_size"
    INT_DISK_FREE = "nutnr_internal_disk_free"
    ODOMETER = "nutnr_fiberlite_odometer"
    TEMP_HS = "nutnr_temperatures_hs"
    TEMP_SP = "nutnr_temperatures_sp"
    TEMP_LM = "nutnr_temperatures_lm"
    HUMIDITY = "nutnr_humidity"
    ELECTRICAL_MN = "nutnr_electrical_mn"
    ELECTRICAL_BD = "nutnr_electrical_bd"
    ELECTRICAL_PR = "nutnr_electrical_pr"
    ELECTRICAL_C = "nutnr_electrical_c"
    LAMP_POWER = "nutnr_lamp_power"
    SPEC_DARK_AV = "nutnr_spec_dark_av"
    SPEC_DARK_SD = "nutnr_spec_dark_sd"
    SPEC_DARK_MI = "nutnr_spec_dark_mi"
    SPEC_DARK_MA = "nutnr_spec_dark_ma"
    SPEC_LIGHT_AV = "nutnr_spec_lght_av"
    SPEC_LIGHT_SD = "nutnr_spec_lght_sd"
    SPEC_LIGHT_MI = "nutnr_spec_lght_mi"
    SPEC_LIGHT_MA = "nutnr_spec_lght_ma"
    TEST_RESULT = "nutnr_test_result"


class SUNATestDataParticle(DataParticle):
    _data_particle_type = DataParticleType.SUNA_TEST

    def _build_parsed_values(self):
        matched = SUNA_TEST_REGEX.match(self.raw_data)

        if not matched:
            raise SampleException("No regex match for test [%s]" %
                                  self.raw_data)
        try:
            parsed_data_list = [
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.EXT_DISK_SIZE, DataParticleKey.VALUE: int(matched.group(1))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.EXT_DISK_FREE, DataParticleKey.VALUE: int(matched.group(2))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.INT_DISK_SIZE, DataParticleKey.VALUE: int(matched.group(3))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.INT_DISK_FREE, DataParticleKey.VALUE: int(matched.group(4))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.ODOMETER, DataParticleKey.VALUE: str(matched.group(5))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.TEMP_HS, DataParticleKey.VALUE: float(matched.group(6))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.TEMP_SP, DataParticleKey.VALUE: float(matched.group(7))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.TEMP_LM, DataParticleKey.VALUE: float(matched.group(8))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.HUMIDITY, DataParticleKey.VALUE: float(matched.group(9))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.ELECTRICAL_MN, DataParticleKey.VALUE: float(matched.group(10))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.ELECTRICAL_BD, DataParticleKey.VALUE: float(matched.group(11))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.ELECTRICAL_PR, DataParticleKey.VALUE: float(matched.group(12))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.ELECTRICAL_C, DataParticleKey.VALUE: float(matched.group(13))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.LAMP_POWER, DataParticleKey.VALUE: int(matched.group(14))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_DARK_AV, DataParticleKey.VALUE: int(matched.group(15))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_DARK_SD, DataParticleKey.VALUE: int(matched.group(16))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_DARK_MI, DataParticleKey.VALUE: int(matched.group(17))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_DARK_MA, DataParticleKey.VALUE: int(matched.group(18))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_LIGHT_AV, DataParticleKey.VALUE: int(matched.group(19))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_LIGHT_SD, DataParticleKey.VALUE: int(matched.group(20))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_LIGHT_MI, DataParticleKey.VALUE: int(matched.group(21))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.SPEC_LIGHT_MA, DataParticleKey.VALUE: int(matched.group(22))},
                {DataParticleKey.VALUE_ID: SUNATestDataParticleKey.TEST_RESULT, DataParticleKey.VALUE: str(matched.group(23))}]

        except ValueError:
            raise SampleException("ValueError while parsing data [%s]" %
                                  self.raw_data)

        return parsed_data_list


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
     #logging level
    __metaclass__ = get_logging_metaclass(log_level='debug')

    #used for storing parameter values before they are changed during DA, used for restoring system
    da_param_restore = []

    def __init__(self, prompts, newline, driver_event):
        """
        Protocol constructor.
        @param prompts A BaseEnum class containing instrument prompts.
        @param newline The newline.
        @param driver_event Driver process event callback.
        """
        # Construct protocol superclass.
        CommandResponseInstrumentProtocol.__init__(self, prompts, newline, driver_event)

        # Set attributes
        self.num_samples = 1  # number of light samples
        self.time_samples = 5  # seconds of light samples
        self._newline = NEWLINE

        # Build protocol state machine.
        self._protocol_fsm = InstrumentFSM(ProtocolState, ProtocolEvent,
                                           ProtocolEvent.ENTER, ProtocolEvent.EXIT)

        # Add event handlers for protocol state machine.
        # UNKNOWN State
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.ENTER, self._handler_unknown_enter)
        self._protocol_fsm.add_handler(ProtocolState.UNKNOWN, ProtocolEvent.DISCOVER, self._handler_unknown_discover)

        # COMMAND State
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.ENTER, self._handler_command_enter)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.ACQUIRE_SAMPLE, self._handler_command_acquire_sample)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.ACQUIRE_STATUS, self._handler_command_acquire_status)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.START_DIRECT, self._handler_command_start_direct)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.START_POLL, self._handler_command_start_poll)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.START_AUTOSAMPLE, self._handler_command_start_autosample)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.GET, self._handler_command_get)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.SET, self._handler_command_set)
        self._protocol_fsm.add_handler(ProtocolState.COMMAND, ProtocolEvent.TEST, self._handler_command_test)

        # DIRECT ACCESS State
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.ENTER, self._handler_direct_access_enter)
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.EXECUTE_DIRECT, self._handler_direct_access_execute_direct)
        self._protocol_fsm.add_handler(ProtocolState.DIRECT_ACCESS, ProtocolEvent.STOP_DIRECT, self._handler_direct_access_stop_direct)

        # POLL State
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.ENTER, self._handler_poll_enter)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.ACQUIRE_SAMPLE, self._handler_poll_acquire_sample)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.MEASURE_N, self._handler_poll_measure_n)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.MEASURE_0, self._handler_poll_measure_0)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.TIMED_N, self._handler_poll_timed_n)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.RESET, self._handler_poll_reset)
        self._protocol_fsm.add_handler(ProtocolState.POLL, ProtocolEvent.STOP_POLL, self._handler_poll_stop_poll)

        # AUTOSAMPLE State
        self._protocol_fsm.add_handler(ProtocolState.AUTOSAMPLE, ProtocolEvent.ENTER, self._handler_autosample_enter)
        self._protocol_fsm.add_handler(ProtocolState.AUTOSAMPLE, ProtocolEvent.RESET, self._handler_autosample_reset)
        self._protocol_fsm.add_handler(ProtocolState.AUTOSAMPLE, ProtocolEvent.STOP_AUTOSAMPLE, self._handler_autosample_stop_autosample)

        # State state machine in UNKNOWN state.
        self._protocol_fsm.start(ProtocolState.UNKNOWN)

        # Add build handlers for device commands.
        self._add_build_handler(InstrumentCommand.GET, self._build_get_command)
        self._add_build_handler(InstrumentCommand.SET, self._build_set_command)
        self._add_build_handler(InstrumentCommand.CMD_LINE, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.SLEEP, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.EXIT, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.STATUS, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.MEASURE, self._build_measure_command)
        self._add_build_handler(InstrumentCommand.TIMED, self._build_timed_command)
        self._add_build_handler(InstrumentCommand.SELFTEST, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.START, self._build_simple_command)
        self._add_build_handler(InstrumentCommand.REBOOT, self._build_simple_command)

        # Add response handlers for device commands.
        self._add_response_handler(InstrumentCommand.GET, self._parse_get_response)
        self._add_response_handler(InstrumentCommand.SET, self._parse_set_response)
        self._add_response_handler(InstrumentCommand.CMD_LINE, self._parse_cmd_line_response)

        # Construct the parameter dictionary containing device parameters,
        # current parameter values, and set formatting functions.
        self._build_param_dict()

        # commands sent sent to device to be filtered in responses for telnet DA
        self._sent_cmds = []

        self._chunker = StringChunker(Protocol.sieve_function)

    @staticmethod
    def sieve_function(raw_data):
        """
        The method that splits samples
        """
        return_list = []

        # look for samples
        for matches in SUNA_SAMPLE_REGEX.finditer(raw_data):
            return_list.append((matches.start(), matches.end()))

        # look for status
        for matches in SUNA_STATUS_REGEX.finditer(raw_data):
            return_list.append((matches.start(), matches.end()))

        # look for test
        for matches in SUNA_TEST_REGEX.finditer(raw_data):
            return_list.append((matches.start(), matches.end()))

        # returns a list of (start, end) tuples for all matches found
        return return_list

    # pretty particle printing
    def _extract_sample(self, particle_class, regex, line, timestamp, publish=True):
        sample = None
        if regex.match(line):
            particle = particle_class(line, port_timestamp=timestamp)
            parsed_sample = particle.generate()
            if publish and self._driver_event:
                self._driver_event(DriverAsyncEvent.SAMPLE, parsed_sample)
                log.info("Parsed sample %r", pprint.pformat(parsed_sample))
            sample = json.loads(parsed_sample)
        return sample

    def _build_param_dict(self):
        """
        Populate the parameter dictionary with parameters.
        For each parameter key, add match stirng, match lambda function,
        and value formatting function for set commands.
        """
        log.debug("_param_dict is %s: %s", self._param_dict, self._param_dict.get_all())

        # TODO!!! WITHOUT STARTUP CONFIG NO REGEX TO MATCH VAL IN CONFIG POSSIBLE (Hence arg 2 is r'') '''

        # DATA ACQUISITION
        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.OPERATION_MODE,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value=InstrumentCommandArgs.POLLED,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Operation Mode",
                             description='Operation mode: Continuous or Polled')

        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.OPERATION_CONTROL,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Samples",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Operation Control",
                             description='Operation control: Samples or Duration')

        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.LIGHT_SAMPLES,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=5,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Light Samples",
                             description='Number of light samples')

        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.DARK_SAMPLES,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=1,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Dark Samples",
                             description='Number of dark samples')

        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.LIGHT_DURATION,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=10,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Light Duration",
                             description='Light duration in seconds',
                             units=Units.SECOND)

        # TODO default value (current default is what was on device, no default in IOS)????
        self._param_dict.add(Parameter.DARK_DURATION,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=5,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Dark Duration",
                             description='Dark duration in seconds',
                             units=Units.SECOND)

        self._param_dict.add(Parameter.POLLED_TIMEOUT,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=65535,
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Polled Timeout",
                             description='Instrument will go to sleep if not polled within time interval',
                             units=Units.SECOND)

        self._param_dict.add(Parameter.SKIP_SLEEP_AT_START,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="ON",
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Skip Sleep at Start",
                             description='Skip putting instrument to sleep at start: On or Off')

        self._param_dict.add(Parameter.COUNTDOWN,
                             r'',
                             lambda match:
                             int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=15,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Countdown",
                             units=Units.SECOND)

        self._param_dict.add(Parameter.REF_MIN_AT_LAMP_ON,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=False,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name="Reference Minute at Lamp-On")

        self._param_dict.add(Parameter.LAMP_STABIL_TIME,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=5,
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Lamp Stability Time",
                             units=ParameterUnit.DECISIEMENS)

        self._param_dict.add(Parameter.LAMP_SWITCH_OFF_TEMPERATURE,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=35,
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Lamp Switch-Off Temperature",
                             description='Temperature at which lamp will turn off',
                             units=Units.DEGREE_CELSIUS)

        self._param_dict.add(Parameter.SPECTROMETER_INTEG_PERIOD,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=False,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name="Spectrometer Integration Period",
                             units=Units.MILLISECOND)

        # INPUT / OUTPUT
        self._param_dict.add(Parameter.MESSAGE_LEVEL,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Info",
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Message Level",
                             description="Level of logging: Error, Warn, Info, Debug")

        self._param_dict.add(Parameter.MESSAGE_FILE_SIZE,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=0,
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Message File Size",
                             units=ParameterUnit.MEGABYTE)

        self._param_dict.add(Parameter.DATA_FILE_SIZE,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=5,
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Data File Size",
                             units=ParameterUnit.MEGABYTE)

        self._param_dict.add(Parameter.OUTPUT_FRAME_TYPE,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Full_ASCII",
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Output Frame Type")

        self._param_dict.add(Parameter.OUTPUT_DARK_FRAME,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Output",
                             visibility=ParameterDictVisibility.IMMUTABLE,
                             display_name="Output Dark Frame")

        # DATA PROCESSING
        self._param_dict.add(Parameter.TEMP_COMPENSATION,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Off",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Temperature Compensation",
                             description="Temperature compensation: On or Off")

        self._param_dict.add(Parameter.FIT_WAVELENGTH_LOW,
                             r'',
                             lambda match: float(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=False,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name="Fit Wavelength Low",
                             units=Units.NANOMETER)

        self._param_dict.add(Parameter.FIT_WAVELENGTH_HIGH,
                             r'',
                             lambda match: float(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=False,
                             direct_access=False,
                             visibility=ParameterDictVisibility.READ_ONLY,
                             display_name="Fit Wavelength High",
                             units=Units.NANOMETER)

        self._param_dict.add(Parameter.FIT_WAVELENGTH_BOTH,
                             r'',
                             lambda match: str(match.group(1)),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="217,240",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Fit Wavelength Both",
                             units=Units.NANOMETER)

        self._param_dict.add(Parameter.CONCENTRATIONS_IN_FIT,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=1,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Concentrations to Fit")

        self._param_dict.add(Parameter.BASELINE_ORDER,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=1,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Baseline Order")

        self._param_dict.add(Parameter.DARK_CORRECTION_METHOD,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="SpecAverage",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Dark Correction Method")

        self._param_dict.add(Parameter.SALINITY_FITTING,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="On",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Salinity Fitting")

        self._param_dict.add(Parameter.BROMIDE_TRACING,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="Off",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Bromide Tracing")

        self._param_dict.add(Parameter.ABSORBANCE_CUTOFF,
                             r'',
                             lambda match: float(match.group(1)),
                             str,
                             type=ParameterDictType.FLOAT,
                             startup_param=True,
                             direct_access=True,
                             default_value=1.3,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Absorbance Cutoff")

        self._param_dict.add(Parameter.INTEG_TIME_ADJUSTMENT,
                             r'',
                             lambda match: match.group(1),
                             str,
                             type=ParameterDictType.STRING,
                             startup_param=True,
                             direct_access=True,
                             default_value="On",
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Integration Time Adjustment")

        self._param_dict.add(Parameter.INTEG_TIME_FACTOR,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=1,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Integration Time Factor",
                             units=Units.SECOND)

        self._param_dict.add(Parameter.INTEG_TIME_STEP,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=20,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Integration Time Step",
                             units=Units.SECOND)

        self._param_dict.add(Parameter.INTEG_TIME_MAX,
                             r'',
                             lambda match: int(match.group(1)),
                             str,
                             type=ParameterDictType.INT,
                             startup_param=True,
                             direct_access=True,
                             default_value=20,
                             visibility=ParameterDictVisibility.READ_WRITE,
                             display_name="Integration Time Max",
                             units=Units.SECOND)

    def _got_chunk(self, chunk, timestamp):
        """
        The base class got_data has gotten a chunk from the chunker.  Pass it to extract_sample
        with the appropriate particle objects and REGEXes.
        """
        try:
            if self._extract_sample(SUNASampleDataParticle, SUNA_SAMPLE_REGEX, chunk, timestamp):
                return
            if self._extract_sample(SUNAStatusDataParticle, SUNA_STATUS_REGEX, chunk, timestamp):
                return
            if self._extract_sample(SUNATestDataParticle, SUNA_TEST_REGEX, chunk, timestamp):
                return
        except SampleException:
            raise SampleException('Error extracting DataParticle')

    def _filter_capabilities(self, events):
        """
        Return a list of currently available capabilities.
        """
        return [x for x in events if Capability.has(x)]

    # def _do_cmd_no_resp(self, cmd, *args, **kwargs):
    #     """
    #     Issue a command to the instrument after clearing of
    #     buffers. No response is handled as a result of the command.
    #
    #     @param cmd The command to execute.
    #     @param args positional arguments to pass to the build handler.
    #     @param timeout=timeout optional wakeup timeout.
    #     @raises InstrumentTimeoutException if the response did not occur in time.
    #     @raises InstrumentProtocolException if command could not be built.
    #     """
    #     timeout = kwargs.get('timeout', 15)
    #     write_delay = kwargs.get('write_delay', 0)
    #
    #     build_handler = self._build_handlers.get(cmd, None)
    #     if not build_handler:
    #         raise InstrumentProtocolException(error_code=InstErrorCode.BAD_DRIVER_COMMAND)
    #     cmd_line = build_handler(cmd, *args)
    #     log.debug("AK DEBUG SENDING CMD LINE %s", cmd_line)
    #
    #     # Clear line and prompt buffers for result.
    #     #self._linebuf = ''
    #     #self._promptbuf = ''
    #
    #     # Send command.
    #     log.debug('_do_cmd_no_resp: %s, timeout=%s' % (repr(cmd_line), timeout))
    #     if write_delay == 0:
    #         self._connection.send(cmd_line)
    #     else:
    #         for char in cmd_line:
    #             self._connection.send(char)
    #             time.sleep(write_delay)

    ########################################################################
    # Unknown handlers.
    ########################################################################

    def _handler_unknown_enter(self):
        """
        Enter unknown state.
        """
        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)

    def _handler_unknown_discover(self):
        """
        Discover current state
        Always starts in command state
        @retval (next_state, result)
        """
        self._wakeup(20)
        log.debug('SENT WAKEUP')
        ret_prompt = self._send_dollar()
        log.debug('SENT DOLLAR prompt = %r', ret_prompt)

        #came from autosampling/polling, need to resend '$' one more time to get it into command mode
        if ret_prompt == Prompt.POLLED:
            ret_prompt = self._send_dollar()
            log.debug('SENT DOLLAR prompt = %r', ret_prompt)

        return ProtocolState.COMMAND, ResourceAgentState.IDLE

    ########################################################################
    # Command handlers.
    ########################################################################

    def _handler_command_enter(self):
        """
        Enter command state.
        @throws InstrumentTimeoutException if the device cannot be woken.
        @throws InstrumentProtocolException if the update commands and not recognized.
        """
        # Command device to initialize parameters and send a config change event.
        self._init_params()

        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)

    def _handler_command_acquire_sample(self):
        """
        Start acquire sample
        """
        next_state = None
        next_agent_state = None
        result = None

        #self._do_cmd_no_resp(InstrumentCommand.SET, Parameter.OPERATION_MODE, "Polled")
        self._do_cmd_no_resp(InstrumentCommand.EXIT)
        self._do_cmd_no_resp(InstrumentCommand.MEASURE, 1)
        self._send_dollar()

        return next_state, (next_agent_state, result)

    def _handler_command_acquire_status(self):
        """
        Start acquire status
        """
        next_state = None
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.STATUS)

        return next_state, (next_agent_state, result)

    def _handler_command_start_direct(self):
        """
        Start direct access
        """
        next_state = ProtocolState.DIRECT_ACCESS
        next_agent_state = ResourceAgentState.DIRECT_ACCESS
        result = None

        log.debug("_handler_command_start_direct: entering DA mode")
        return next_state, (next_agent_state, result)

    def _handler_command_start_poll(self):
        """
        Start polling
        """
        next_state = ProtocolState.POLL
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.SET, Parameter.OPERATION_MODE, InstrumentCommandArgs.POLLED)
        self._do_cmd_no_resp(InstrumentCommand.EXIT)

        return next_state, (next_agent_state, result)

    def _handler_command_start_autosample(self):
        """
        Start autosampling
        """
        next_state = ProtocolState.AUTOSAMPLE
        next_agent_state = ResourceAgentState.STREAMING
        result = None

        self._do_cmd_no_resp(InstrumentCommand.SET, Parameter.OPERATION_MODE, InstrumentCommandArgs.CONTINUOUS)
        self._do_cmd_no_resp(InstrumentCommand.EXIT)

        return next_state, (next_agent_state, result)

    def _handler_command_get(self, params=None):
        """
        Get parameter(s)
        @param params List of parameters to get
        """
        next_state = None
        result = {}


        log.debug("GET FOR: %s", params)

        if params == Parameter.ALL:
            params = self._param_dict.get_keys()
        elif not params or not isinstance(params, list):
            raise InstrumentParameterException("Params must be a list")
        else:
            for param in params:
                if not Parameter.has(param):
                    raise InstrumentParameterException("%s is not a parameter" % param)

                # handle driver parameters
                if param == Parameter.NUM_LIGHT_SAMPLES:
                    result[param] = self.num_samples
                elif param == Parameter.TIME_LIGHT_SAMPLE:
                    result[param] = self.time_samples
                # handle instrument parameters
                else:
                    #wfitboth is a set only param and cannot be read from the instrument
                    if param == Parameter.FIT_WAVELENGTH_BOTH:
                        result[param] = self._param_dict.get(Parameter.FIT_WAVELENGTH_BOTH)
                    else:
                        type_func = PARAM_TYPE_FUNC.get(param)
                        result[param] = type_func(self._get_from_instrument(param))  # always get str type from instrument

        log.debug("Get finished, next: %s, result: %s,", next_state, result)
        return next_state, result

    def _handler_command_set(self, params, *args):
        """
        Set parameter
        """
        next_state = None

        self._set_params(params, *args)

        return next_state, None

    def _set_params(self, *args, **kwargs):
        """
        Used to set the parameters when startup config is set by _init_params call
        """
        try:
            params = args[0]

            if params is None or not isinstance(params, dict):
                raise InstrumentParameterException()

        except IndexError:
            raise InstrumentParameterException('Set command requires a parameter dict.')

        self._verify_not_readonly(*args, **kwargs)

        old_config = self._param_dict.get_config()
        log.debug("OLD CONFIG: %s", self._param_dict.get_config())

        for (key, val) in params.iteritems():
            log.debug("KEY = %s VALUE = %s", key, val)
            # check for driver parameters
            if key == Parameter.NUM_LIGHT_SAMPLES:
                self.num_samples = params[key]
            elif key == Parameter.TIME_LIGHT_SAMPLE:
                self.time_samples = params[key]
            else:
                if not Parameter.has(key):
                    raise InstrumentParameterException("%s is not a parameter" % key)

                if self._param_dict.get(key) != params[key]:    # if already set to "new" value we are done
                    try:
                        str_val = self._param_dict.format(key, params[key])
                    except KeyError:
                        raise InstrumentParameterException()

                    self._do_cmd_resp(InstrumentCommand.SET, key, str_val,
                              timeout=100,
                              response_regex=re.compile(Prompt.SET_OK))
                    self._param_dict.set_value(key, params[key])

        new_config = self._param_dict.get_config()
        log.debug("NEW CONFIG: %s", self._param_dict.get_config())

        if new_config != old_config:
            self._driver_event(DriverAsyncEvent.CONFIG_CHANGE)

    def _handler_command_test(self):
        """
        Test the instrument state
        """
        next_state = None
        next_state_agent = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.SELFTEST)

        return next_state, (next_state_agent, result)

    def _handler_command_exit(self):
        """
        Exit the command state
        """

        self._do_cmd_no_resp(InstrumentCommand.EXIT)
        self._do_cmd_no_resp(InstrumentCommand.SLEEP)

        return ProtocolState.UNKNOWN, (None, None)

    ########################################################################
    # Direct access handlers.
    ########################################################################

    def _handler_direct_access_enter(self):
        """
        Enter direct access state.
        """
        #get the DA params and store their values for future use in restoring the state after leaving DA
        da_params = self.get_direct_access_params()
        self.da_param_restore = {}
        for param in da_params:
            self.da_param_restore[param] = self._param_dict.get(param)

        log.debug(' SAVED da_param_restore %r', self.da_param_restore)

        # Tell driver superclass to send a state change event.
        # Superclass will query the state.
        self._driver_event(DriverAsyncEvent.STATE_CHANGE)
        self._sent_cmds = []

    def _handler_direct_access_execute_direct(self, data):
        """
        """
        next_state = None
        result = None
        next_agent_state = None

        self._do_cmd_direct(data)

        # add sent command to list for 'echo' filtering in callback
        self._sent_cmds.append(data)

        return next_state, (next_agent_state, result)

    def _handler_direct_access_stop_direct(self):
        """
        @throw InstrumentProtocolException on invalid command
        """
        result = None
        next_state = ProtocolState.COMMAND
        next_agent_state = ResourceAgentState.COMMAND

        #restore DA params
        log.debug("da_param_restore = %s,", self.da_param_restore)
        self._set_params(self.da_param_restore, startup=True)

        return next_state, (next_agent_state, result)

    ########################################################################
    # Poll handlers.
    ########################################################################

    def _handler_poll_enter(self):
        """
        Enter poll state
        """
        next_state = None
        result = None

        self._driver_event(DriverAsyncEvent.STATE_CHANGE)
        return next_state, result

    def _handler_poll_acquire_sample(self):
        """
        Get a sample from the SUNA
        """
        next_state = None
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.MEASURE, 1)

        return next_state, (next_agent_state, result)

    def _handler_poll_measure_n(self):
        """
        Measure N Light Samples
        """
        next_state = None
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.MEASURE, self.num_samples, timeout=100)

        return next_state, (next_agent_state, result)

    def _handler_poll_measure_0(self):
        """
        Measure 0 Dark Sample
        """
        next_state = None
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.MEASURE, 0)

        return next_state, (next_agent_state, result)

    def _handler_poll_timed_n(self):
        """
        Timed Sampling for N time
        """
        next_state = None
        next_agent_state = None
        result = None

        self._do_cmd_no_resp(InstrumentCommand.TIMED, self.time_samples, timeout=100)

        return next_state, (next_agent_state, result)

    def _handler_poll_reset(self):
        """
        reset the device
        """
        next_state = None
        next_agent_state = None
        result = None

        self._wakeup(20)        # if device is already awake and in polled mode this won't do anything
        self._do_cmd_no_resp(InstrumentCommand.CMD_LINE)  # go to cmd line
        self._do_cmd_no_resp(InstrumentCommand.REBOOT, timeout=100)  # reboot the device

        return next_state, (next_agent_state, result)

    def _handler_poll_stop_poll(self):
        """
        Exit the poll state
        """
        result = None

        try:
            self._wakeup(20)        # if device is already awake and in polled mode this won't do anything
            self._send_dollar()     # send a "$" to get the device back to command mode
            next_state = ProtocolState.COMMAND
            next_agent_state = ResourceAgentState.COMMAND
        except InstrumentException:
            raise InstrumentProtocolException(error_code=InstErrorCode.HARDWARE_ERROR,
                                              msg="Could not interrupt hardware!")

        return next_state, (next_agent_state, result)

    ########################################################################
    # Autosample handlers.
    ########################################################################

    def _handler_autosample_enter(self):
        """
        Enter autosample state
        """
        next_state = None
        result = None

        self._driver_event(DriverAsyncEvent.STATE_CHANGE)
        return next_state, result

    def _handler_autosample_reset(self):
        """
        reset the device
        """
        next_state = ProtocolState.POLL
        next_agent_state = ResourceAgentState.COMMAND
        result = None

        self._do_cmd_no_resp(InstrumentCommand.CMD_LINE)
        self._wakeup(20)        # if device is already awake and in polled mode this won't do anything
        self._do_cmd_no_resp(InstrumentCommand.CMD_LINE)  # go to cmd line
        self._do_cmd_no_resp(InstrumentCommand.SET, Parameter.OPERATION_MODE, InstrumentCommandArgs.POLLED)  # DONT RETURN TO AUTOSAMPLING
        self._do_cmd_no_resp(InstrumentCommand.REBOOT, timeout=100)  # reboot the device

        return next_state, (next_agent_state, result)

    def _handler_autosample_stop_autosample(self):
        """
        Exit the autosample state
        """
        result = None

        self._do_cmd_no_resp(InstrumentCommand.CMD_LINE)
        #time.sleep(15)      # anything done in these 15 seconds can cause undefined behavior in the instrument
        self._wakeup(20)
        self._do_cmd_no_resp(InstrumentCommand.CMD_LINE)
        next_state = ProtocolState.COMMAND
        next_agent_state = ResourceAgentState.COMMAND

        return next_state, (next_agent_state, result)

    ########################################################################
    # Build handlers
    ########################################################################
    def _build_get_command(self, cmd, param):
        """
        Build a command to get the desired argument.

        @param cmd The command being used (Command.GET in this case)
        @param param The name of the parameter to get
        @retval Returns string ready for sending to instrument
        """
        if not Parameter.has(param):
            raise InstrumentParameterException("%s is not a parameter" % param)
        return "%s %s%s" % (InstrumentCommand.GET, param, NEWLINE)

    def _build_set_command(self, cmd, param, value):
        """
        Build a command to set the desired argument

        @param cmd The command being used (Command.SET in this case)
        @param param The name of the parameter to set
        @value The value to set the parameter to
        @retval Returns string ready for sending to instrument
        """
        if not Parameter.has(param):
            raise InstrumentParameterException("%s is not a parameter" % param)
        return "%s %s %s%s" % (InstrumentCommand.SET, param, value, NEWLINE)

    def _build_measure_command(self, cmd, samples):
        """
        Build a command to take samples

        @param cmd The command, "Measure"
        @param samples The number of light samples to take
        @retval Returns string ready for sending to instrument
        """
        if samples > 0:
            raise InstrumentParameterException("Sample count cannot be less than 0: " % samples)
        assert samples >= 0  # negative samples is not valid
        return "%s %s%s" % (InstrumentCommand.MEASURE, samples, NEWLINE)

    def _build_timed_command(self, cmd, time_amount):
        """
        Build a command to take samples

        @param cmd The command, "Timed"
        @param time_amount The amount of time to sample for
        @retval Returns string ready for sending to instrument
        """
        if time_amount > 0:
            raise InstrumentParameterException("Time to sample cannot be less than 0: " % time_amount)
        return "%s %s%s" % (InstrumentCommand.TIMED, time_amount, NEWLINE)

    ########################################################################
    # Response handlers
    ########################################################################
    def _parse_set_response(self, response, prompt):
        """
        Determine if a set was successful or not

        @param response What was sent back from the command that was sent
        """
        log.debug("SET response %s", response)
        if re.match(Prompt.ERROR, response):
            raise InstrumentProtocolException("Error occurred for command SET: (%r)" % response)

        return True

    def _parse_get_response(self, response, prompt):
        """
        Parse the response from the instrument for a couple of different
        query responses.

        @param response The response string from the instrument
        @retval return The numerical value of the parameter in the known units
        @raise InstrumentProtocolException When a bad response is encountered
        """
        if re.match(Prompt.ERROR, response):
            raise InstrumentProtocolException("Error occurred for command GET: (%r)" % response)

        return response

    def _parse_cmd_line_response(self, response, prompt):
        """
        Parse the response from the instrument for a $ command.

        @param response The response string from the instrument
        @param prompt The prompt received from the instrument
        @retval return The response as is, None is there is no response
        """
        for search_prompt in (Prompt.POLLED, Prompt.COMMAND):
            start = response.find(search_prompt)
            if start != -1:
                log.debug("_parse_cmd_line_response: response=%r", response[start:start+len(search_prompt)])
                return response[start:start+len(search_prompt)]

        return None

    ########################################################################
    # Helpers
    ########################################################################
    def _get_from_instrument(self, param):
        """
        instruct the instrument to get a parameter value from the instrument
        @param param: name of the parameter
        @return: value read from the instrument.  None otherwise.
        @raise: InstrumentProtocolException when fail to get a response from the instrument
        """
        for attempt in xrange(RETRY):
            # retry up to RETRY times
            try:
                val = self._do_cmd_resp(InstrumentCommand.GET, param,
                                        timeout=100,
                                        response_regex=re.compile(Prompt.OK))
                return val
            except InstrumentProtocolException as ex:
                pass   # GET failed, so retry again
        else:
            log.debug('FAILED TO GET PARAM: %s', param)
            # retries exhausted, so raise exception
            raise ex

    def _get_from_param_dict(self, param):
        return self._param_dict.get(param, 0)

    def _send_wakeup(self):
        """Send a wakeup to this instrument...one that wont hurt if it is awake
        already."""
        self._connection.send(NEWLINE)

    def _send_dollar(self, timeout=15):
        """
        Send a blind $ command to the device
        """
        log.debug("Sending $ char")

        ret_prompt = self._do_cmd_resp(InstrumentCommand.CMD_LINE, timeout=timeout,
                             expected_prompt=[Prompt.COMMAND, Prompt.POLLED])

        return ret_prompt

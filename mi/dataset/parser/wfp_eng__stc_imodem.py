#!/usr/bin/env python

"""
@package mi.dataset.parser.wfp_eng__stc_imodem
@file marine-integrations/mi/dataset/parser/wfp_eng__stc_imodem.py
@author Emily Hahn
@brief Parser for the WFP_ENG__STC_IMODEM dataset driver
Release notes:

initial release
"""

__author__ = 'Emily Hahn'
__license__ = 'Apache 2.0'

import copy
import re
import ntplib

from mi.core.log import get_logger ; log = get_logger()
from mi.core.common import BaseEnum
from mi.core.instrument.data_particle import DataParticle, DataParticleKey
from mi.core.exceptions import SampleException, DatasetParserException
from mi.dataset.parser.WFP_E_file_common import WfpEFileParser, DATA_SAMPLE_MATCHER, PROFILE_MATCHER, START_TIME_MATCHER
from mi.dataset.dataset_parser import Parser


class DataParticleType(BaseEnum):
    START_TIME = 'wfp_eng__stc_imodem_start_time'
    STATUS = 'wfp_eng__stc_imodem_status'
    ENGINEERING = 'wfp_eng__stc_imodem_engineering'

class Wfp_eng__stc_imodem_statusParserDataParticleKey(BaseEnum):
    INDICATOR = 'indicator'
    RAMP_STATUS = 'ramp_status'
    PROFILE_STATUS = 'profile_status'
    SENSOR_STOP = 'sensor_stop'
    PROFILE_STOP = 'profile_stop'

    
class Wfp_eng__stc_imodem_statusParserDataParticle(DataParticle):
    """
    Class for parsing data from the WFP_ENG__STC_IMODEM data set
    """

    _data_particle_type = DataParticleType.STATUS

    def _build_parsed_values(self):
        """
        Take something in the data format and turn it into
        a particle with the appropriate tag.
        @throws SampleException If there is a problem with sample creation
        """
        match_prof = PROFILE_MATCHER.match(self.raw_data)

        if not match_ss or not match_prof:
            raise SampleException("Wfp_eng__stc_imodem_statusParserDataParticle: No regex match of parsed sample data: [%s]",
                                  self.raw_data)

        try:
            fields_prof = struct.unpack('<ihhII', match_prof.group(0))
            indicator = int(fields_prof[0])
            ramp_status = int(fields_prof[1])
            profile_status = int(fields_prof[2])
            profile_stop = int(fields_prof[3])
            sensor_stop = int(fields_prof[4])
        except (ValueError, TypeError, IndexError) as ex:
            raise SampleException("Error (%s) while decoding parameters in data: [%s]"
                                  % (ex, match.group(0)))

        result = [{DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.INDICATOR,
                   DataParticleKey.VALUE: indicator},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.RAMP_STATUS,
                   DataParticleKey.VALUE: ramp_status},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.PROFILE_STATUS,
                   DataParticleKey.VALUE: profile_status},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.SENSOR_STOP,
                   DataParticleKey.VALUE: sensor_stop},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.PROFILE_STOP,
                   DataParticleKey.VALUE: profile_stop}]
        log.debug('Wfp_eng__stc_imodem_statusParserDataParticle: particle=%s', result)
        return result

    def __eq__(self, arg):
        """
        Quick equality check for testing purposes. If they have the same raw
        data, timestamp, and new sequence, they are the same enough for this 
        particle
        """
        if ((self.raw_data == arg.raw_data) and \
            (self.contents[DataParticleKey.INTERNAL_TIMESTAMP] == \
             arg.contents[DataParticleKey.INTERNAL_TIMESTAMP])):
            return True
        else:
            if self.raw_data != arg.raw_data:
                log.debug('Raw data does not match')
            elif self.contents[DataParticleKey.INTERNAL_TIMESTAMP] != \
                 arg.contents[DataParticleKey.INTERNAL_TIMESTAMP]:
                log.debug('Timestamp does not match')
            return False

class Wfp_eng__stc_imodem_startParserDataParticleKey(BaseEnum):
    SENSOR_START = 'sensor_start'
    PROFILE_START = 'profile_start'

class Wfp_eng__stc_imodem_startParserDataParticle(DataParticle):
    """
    Class for parsing data from the WFP_ENG__STC_IMODEM data set
    """

    _data_particle_type = DataParticleType.START_TIME

    def _build_parsed_values(self):
        """
        Take something in the data format and turn it into
        a particle with the appropriate tag.
        @throws SampleException If there is a problem with sample creation
        """
        match_ss = START_TIME_MATCHER.match(self.raw_data)

        if not match_ss or not match_prof:
            raise SampleException("Wfp_eng__stc_imodem_startParserDataParticle: No regex match of parsed sample data: [%s]",
                                  self.raw_data)

        try:
            fields_ss = struct.unpack('<II', match_ss.group(0))
            sensor_start = int(fields_ss[0])
            profile_start = int(fields_ss[1])
        except (ValueError, TypeError, IndexError) as ex:
            raise SampleException("Error (%s) while decoding parameters in data: [%s]"
                                  % (ex, match.group(0)))

        result = [{DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.SENSOR_START,
                   DataParticleKey.VALUE: sensor_start},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_profilerParserDataParticleKey.PROFILE_START,
                   DataParticleKey.VALUE: profile_start}]
        log.debug('Wfp_eng__stc_imodem_startParserDataParticle: particle=%s', result)
        return result

    def __eq__(self, arg):
        """
        Quick equality check for testing purposes. If they have the same raw
        data, timestamp, and new sequence, they are the same enough for this 
        particle
        """
        if ((self.raw_data == arg.raw_data) and \
            (self.contents[DataParticleKey.INTERNAL_TIMESTAMP] == \
             arg.contents[DataParticleKey.INTERNAL_TIMESTAMP])):
            return True
        else:
            if self.raw_data != arg.raw_data:
                log.debug('Raw data does not match')
            elif self.contents[DataParticleKey.INTERNAL_TIMESTAMP] != \
                 arg.contents[DataParticleKey.INTERNAL_TIMESTAMP]:
                log.debug('Timestamp does not match')
            return False



class Wfp_eng__stc_imodem_engineeringParserDataParticleKey(BaseEnum):
    TIMESTAMP = 'timestamp'
    PROF_CURRENT = 'prof_current'
    PROF_VOLTAGE = 'prof_voltage'
    PROF_PRESSURE = 'prof_pressure'

class Wfp_eng__stc_imodem_engineeringParserDataParticle(DataParticle):
    """
    Class for parsing data from the WFP_ENG__STC_IMODEM data set
    """

    _data_particle_type = DataParticleType.ENGINEERING

    def _build_parsed_values(self):
        """
        Take something in the data format and turn it into
        a particle with the appropriate tag.
        @throws SampleException If there is a problem with sample creation
        """
        match = DATA_SAMPLE_MATCHER.match(self.raw_data)
        if not match:
            raise SampleException("Wfp_eng__stc_imodem_engineeringParserDataParticle: No regex match of parsed sample data: [%s]",
                                  self.raw_data)
        try:
            fields = struct.unpack('<Ifff', match.group(0)[:16])
            timestamp = int(fields[0])
            profile_current = float(fields[1])
            profile_voltage = float(fields[2])
            profile_pressure = float(fields[3])
        except(ValueError, TypeError, IndexError) as ex:
            raise SampleException("Error (%s) while decoding parameters in data: [%s]"
                                  % (ex, match.group(0)))

        result = [{DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_engineeringParserDataParticleKey.TIMESTAMP,
                   DataParticleKey.VALUE: indicator},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_engineeringParserDataParticleKey.PROF_CURRENT,
                   DataParticleKey.VALUE: ramp_status},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_engineeringParserDataParticleKey.PROF_VOLTAGE,
                   DataParticleKey.VALUE: profile_status},
                  {DataParticleKey.VALUE_ID: Wfp_eng__stc_imodem_engineeringParserDataParticleKey.PROF_PRESSURE,
                   DataParticleKey.VALUE: sensor_stop}]
        log.debug('Wfp_eng__stc_imodem_engineeringParserDataParticle: particle=%s', result)
        return result

    def __eq__(self, arg):
        """
        Quick equality check for testing purposes. If they have the same raw
        data, timestamp, and new sequence, they are the same enough for this 
        particle
        """
        if ((self.raw_data == arg.raw_data) and \
            (self.contents[DataParticleKey.INTERNAL_TIMESTAMP] == \
             arg.contents[DataParticleKey.INTERNAL_TIMESTAMP])):
            return True
        else:
            if self.raw_data != arg.raw_data:
                log.debug('Raw data does not match')
            elif self.contents[DataParticleKey.INTERNAL_TIMESTAMP] != \
                 arg.contents[DataParticleKey.INTERNAL_TIMESTAMP]:
                log.debug('Timestamp does not match')
            return False

class Wfp_eng__stc_imodemParser(WfpEFileParser):

    def parse_start_time(self, data):
        """
        Parse the start time of the profile and the sensor
        """
        if START_TIME_MATCHER.match(data):
            self._timestamp = 0 # what to use for timestamp???
            sample = self._extract_sample(Wfp_eng__stc_imodem_startParserDataParticle, START_TIME_MATCHER,
                                          data, self._timestamp)
            if sample:
                # create particle
                log.trace("Extracting sample %s with read_state: %s", data, self._read_state)
                self._increment_state(end, self._timestamp)
                result_particle = (sample, copy.copy(self._read_state))

    def parse_record(self, record):
        """
        determine if this is a engineering or data record and parse
        """
        sample = None
        result_particle = []
        if PROFILE_MATCHER.match(record):
            # send to WFP_eng_profiler if WFP
            self._timestamp = 0 # what to use for timestamp???
            sample = self._extract_sample(Wfp_eng__stc_imodem_profilerParserDataParticle, PROFILE_MATCHER,
                                          record, self._timestamp)
        else if DATA_SAMPLE_MATCHER.match(record):
            # pull out the timestamp for this record
            match = DATA_SAMPLE_MATCHER.match(record)
            fields = struct.unpack('<I', match.group(0)[:4])
            timestamp = int(fields[0])
            self._timestamp = ntplib.system_to_ntp_time(timestamp)
            log.debug("Converting record timestamp %f to ntp timestamp %f", timestamp, self._timestamp)
            sample = self._extract_sample(Wfp_eng__stc_imodem_engineeringParserDataParticle, DATA_SAMPLE_MATCHER,
                                          record, self._timestamp)
        if sample:
            # create particle
            log.trace("Extracting sample %s with read_state: %s", record, self._read_state)
            self._increment_state(end, self._timestamp)    
            result_particle = (sample, copy.copy(self._read_state))
                    
        return result_particle





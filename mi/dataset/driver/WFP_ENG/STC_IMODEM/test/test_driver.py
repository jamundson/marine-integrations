"""
@package mi.dataset.driver.WFP_ENG.STC_IMODEM.test.test_driver
@file marine-integrations/mi/dataset/driver/WFP_ENG/STC_IMODEM/driver.py
@author Emily Hahn
@brief Test cases for WFP_ENG__STC_IMODEM driver

USAGE:
 Make tests verbose and provide stdout
   * From the IDK
       $ bin/dsa/test_driver
       $ bin/dsa/test_driver -i [-t testname]
       $ bin/dsa/test_driver -q [-t testname]
"""

__author__ = 'Emily Hahn'
__license__ = 'Apache 2.0'

import unittest

from nose.plugins.attrib import attr
from mock import Mock

from mi.core.log import get_logger ; log = get_logger()
from mi.idk.exceptions import SampleTimeout

from mi.idk.dataset.unit_test import DataSetTestCase
from mi.idk.dataset.unit_test import DataSetIntegrationTestCase
from mi.idk.dataset.unit_test import DataSetQualificationTestCase
from mi.dataset.dataset_driver import DataSourceConfigKey, DataSetDriverConfigKeys

from mi.dataset.driver.WFP_ENG.STC_IMODEM.driver import WFP_ENG__STC_IMODEM_DataSetDriver
from mi.dataset.parser.wfp_eng__stc_imodem import Wfp_eng__stc_imodem_statusParserDataParticle
from mi.dataset.parser.wfp_eng__stc_imodem import Wfp_eng__stc_imodem_startParserDataParticle
from mi.dataset.parser.wfp_eng__stc_imodem import Wfp_eng__stc_imodem_engineeringParserDataParticle

# Fill in driver details
DataSetTestCase.initialize(
    driver_module='mi.dataset.driver.WFP_ENG.STC_IMODEM.driver',
    driver_class='WFP_ENG__STC_IMODEM_DataSetDriver',
    agent_resource_id = '123xyz',
    agent_name = 'Agent007',
    agent_packet_config = WFP_ENG__STC_IMODEM_DataSetDriver.stream_config(),
    startup_config = {
        DataSourceConfigKey.RESOURCE_ID: 'wfp_eng__stc_imodem',
        DataSourceConfigKey.HARVESTER:
        {
            DataSetDriverConfigKeys.DIRECTORY: '/tmp/dsatest',
            DataSetDriverConfigKeys.PATTERN: 'E*.DAT',
            DataSetDriverConfigKeys.FREQUENCY: 1,
        },
        DataSourceConfigKey.PARSER: {}
    }
)

SAMPLE_STREAM = 'wfp_eng__stc_imodem_parsed'

###############################################################################
#                            INTEGRATION TESTS                                #
# Device specific integration tests are for                                   #
# testing device specific capabilities                                        #
###############################################################################
@attr('INT', group='mi')
class IntegrationTest(DataSetIntegrationTestCase):
 
    def test_get(self):
        """
        Test that we can get data from files.  Verify that the driver
        sampling can be started and stopped
        """
        self.clear_sample_data()

        # Start sampling and watch for an exception
        self.driver.start_sampling()

        self.clear_async_data()
        self.create_sample_data('first.DAT', "E0000001.DAT")
        self.assert_data(Wfp_eng__stc_imodem_startParserDataParticle, 'first_start.result.yml', count=1, timeout=10)
        self.assert_data(Wfp_eng__stc_imodem_engineeringParserDataParticle, 'first_eng.result.yml', count=1, timeout=10)

        self.clear_async_data()
        self.create_sample_data('second.DAT', "E0000002.DAT")
        # start is the same particle here, just use the same results
        self.assert_data(Wfp_eng__stc_imodem_startParserDataParticle, 'first_start.result.yml', count=1, timeout=10)
        self.assert_data(Wfp_eng__stc_imodem_engineeringParserDataParticle, 'second_eng.result.yml', count=4, timeout=10)

        self.clear_async_data()
        self.create_sample_data('E0000303.DAT', "E0000303.DAT")
        # start is the same particle here, just use the same results
        self.assert_data(Wfp_eng__stc_imodem_startParserDataParticle, 'first_start.result.yml', count=1, timeout=10)
        self.assert_data(Wfp_eng__stc_imodem_engineeringParserDataParticle, 'E0000303_eng.result.yml', count=31, timeout=10)
        self.assert_data(Wfp_eng__stc_imodem_statusParserDataParticle, 'E0000303_status.result.yml', count=1, timeout=10)

    def test_stop_resume(self):
        """
        Test the ability to stop and restart the process
        """
        pass

###############################################################################
#                            QUALIFICATION TESTS                              #
# Device specific qualification tests are for                                 #
# testing device specific capabilities                                        #
###############################################################################
@attr('QUAL', group='mi')
class QualificationTest(DataSetQualificationTestCase):
    def setUp(self):
        super(QualificationTest, self).setUp()

    def test_publish_path(self):
        """
        Setup an agent/driver/harvester/parser and verify that data is
        published out the agent
        """
        pass

    def test_large_import(self):
        """
        Test importing a large number of samples from the file at once
        """
        pass

    def test_stop_start(self):
        """
        Test the agents ability to start data flowing, stop, then restart
        at the correct spot.
        """
        pass

    def test_parser_exception(self):
        """
        Test an exception is raised after the driver is started during
        record parsing.
        """
        pass


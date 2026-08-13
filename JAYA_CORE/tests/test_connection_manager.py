"""
Unit tests for the ConnectionManager.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock

# We need to import the ConnectionManager from the module.
# Since we are in the tests directory, we can adjust the sys.path.
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai_connectors.connection_manager import ConnectionManager

class TestConnectionManager(unittest.TestCase):

    def setUp(self):
        # We'll mock the dependencies: LocalLLMAdapter, LANSyncClient, PublicAPIClient
        self.local_adapter_patch = patch('ai_connectors.connection_manager.LocalLLMAdapter')
        self.lan_client_patch = patch('ai_connectors.connection_manager.LANSyncClient')
        self.internet_client_patch = patch('ai_connectors.connection_manager.PublicAPIClient')
        self.mock_local_adapter = self.local_adapter_patch.start()
        self.mock_lan_client = self.lan_client_patch.start()
        self.mock_internet_client = self.internet_client_patch.start()

        # Also mock the value scoring function
        self.value_scoring_patch = patch('ai_connectors.connection_manager.evaluate_intent_value')
        self.mock_value_scoring = self.value_scoring_patch.start()

        # Mock the filters
        self.filter_inbound_patch = patch('ai_connectors.connection_manager.filter_inbound')
        self.mock_filter_inbound = self.filter_inbound_patch.start()
        self.sanitize_outbound_patch = patch('ai_connectors.connection_manager.sanitize_outbound')
        self.mock_sanitize_outbound = self.sanitize_outbound_patch.start()

        # Set up the mocks to return sensible defaults
        self.mock_local_adapter_instance = Mock()
        self.mock_local_adapter.return_value = self.mock_local_adapter_instance
        self.mock_local_adapter_instance.generate.return_value = "Local response"

        self.mock_lan_client_instance = Mock()
        self.mock_lan_client.return_value = self.mock_lan_client_instance
        self.mock_lan_client_instance.query.return_value = "LAN response"

        self.mock_internet_client_instance = Mock()
        self.mock_internet_client.return_value = self.mock_internet_client_instance
        self.mock_internet_client_instance.query.return_value = "Internet response"

        self.mock_value_scoring.return_value = 0.8  # high enough to allow external

        self.mock_filter_inbound.side_effect = lambda x: x  # just return the input
        self.mock_sanitize_outbound.side_effect = lambda x: x  # just return the input

        # Create the manager
        self.manager = ConnectionManager(
            local_model_path="dummy.gguf",
            lan_server_addr="127.0.0.1",
            internet_allowed=True,
            value_threshold=0.5
        )

    def tearDown(self):
        self.local_adapter_patch.stop()
        self.lan_client_patch.stop()
        self.internet_client_patch.stop()
        self.value_scoring_patch.stop()
        self.filter_inbound_patch.stop()
        self.sanitize_outbound_patch.stop()

    def test_local_response_used(self):
        # When local response is sufficient, it should be used.
        self.mock_local_adapter_instance.generate.return_value = "Good local response"
        self.mock_local_adapter_instance.generate.return_value = "Good local response"
        result = self.manager.get_response("Hello")
        self.mock_local_adapter_instance.generate.assert_called_once()
        # We expect the local response to be returned
        self.assertEqual(result, "Good local response")
        # LAN and internet should not be called
        self.mock_lan_client_instance.query.assert_not_called()
        self.mock_internet_client_instance.query.assert_not_called()

    def test_lan_used_when_local_insufficient(self):
        # Local returns insufficient (short string)
        self.mock_local_adapter_instance.generate.return_value = "Hi"
        # LAN returns a good response
        self.mock_lan_client_instance.query.return_value = "Good LAN response"
        result = self.manager.get_response("Hello")
        self.assertEqual(result, "Good LAN response")
        self.mock_local_adapter_instance.generate.assert_called_once()
        self.mock_lan_client_instance.query.assert_called_once()
        self.mock_internet_client_instance.query.assert_not_called()

    def test_internet_used_when_local_and_lan_insufficient(self):
        self.mock_local_adapter_instance.generate.return_value = "Hi"
        self.mock_lan_client_instance.query.return_value = "Hey"
        self.mock_internet_client_instance.query.return_value = "Good internet response"
        result = self.manager.get_response("Hello")
        self.assertEqual(result, "Good internet response")
        self.mock_local_adapter_instance.generate.assert_called_once()
        self.mock_lan_client_instance.query.assert_called_once()
        self.mock_internet_client_instance.query.assert_called_once()

    def test_fallback_when_all_fail(self):
        self.mock_local_adapter_instance.generate.return_value = "Hi"
        self.mock_lan_client_instance.query.return_value = "Hey"
        self.mock_internet_client_instance.query.return_value = ""
        result = self.manager.get_response("Hello")
        # The fallback message is defined in _fallback_response
        self.assertIn("Maaf, saya tidak dapat menemukan jawaban", result)

    def test_internet_disabled(self):
        manager = ConnectionManager(
            local_model_path="dummy.gguf",
            lan_server_addr="127.0.0.1",
            internet_allowed=False,
            value_threshold=0.5
        )
        self.mock_local_adapter_instance.generate.return_value = "Hi"
        self.mock_lan_client_instance.query.return_value = "LAN response"
        result = manager.get_response("Hello")
        self.assertEqual(result, "LAN response")
        self.mock_internet_client_instance.query.assert_not_called()

    def test_value_blocks_external(self):
        # Set value score low so that external is not allowed
        self.mock_value_scoring.return_value = 0.4  # below threshold 0.5
        self.mock_local_adapter_instance.generate.return_value = "Hi"  # insufficient
        self.mock_lan_client_instance.query.return_value = "LAN response"
        # Even though LAN should be used
        result = self.manager.get_response("Hello")
        self.assertEqual(result, "LAN response")
        # Internet should not be called because value is low
        self.mock_internet_client_instance.query.assert_not_called()

if __name__ == '__main__':
    unittest.main()
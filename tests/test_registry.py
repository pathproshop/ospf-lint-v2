"""
Unit tests for parser auto-discovery and registry.
"""

import pytest
from parsers import PARSERS, get_parser, get_supported_platforms
from parsers.base import OSPFParser


class TestParserRegistry:
    """Test parser auto-discovery and registration."""
    
    def test_parsers_registered(self):
        """Should have at least the built-in parsers registered."""
        assert len(PARSERS) >= 3
    
    def test_junos_registered(self):
        assert 'juniper_junos' in PARSERS
    
    def test_xr_registered(self):
        assert 'cisco_xr' in PARSERS
    
    def test_ios_registered(self):
        assert 'cisco_ios' in PARSERS
    
    def test_get_parser_returns_class(self):
        parser = get_parser('juniper_junos')
        assert parser is not None
        assert issubclass(parser, OSPFParser)
    
    def test_get_parser_unknown_returns_none(self):
        parser = get_parser('unknown_platform')
        assert parser is None
    
    def test_get_supported_platforms(self):
        platforms = get_supported_platforms()
        assert isinstance(platforms, list)
        assert 'juniper_junos' in platforms
        assert 'cisco_xr' in platforms
        assert 'cisco_ios' in platforms


class TestParserInterface:
    """Test that all registered parsers implement required interface."""
    
    def test_all_parsers_have_device_type(self):
        for device_type, parser in PARSERS.items():
            assert parser.device_type == device_type
    
    def test_all_parsers_have_ospf_commands(self):
        for device_type, parser in PARSERS.items():
            assert parser.ospf_commands is not None
            assert isinstance(parser.ospf_commands, list)
            assert len(parser.ospf_commands) > 0
    
    def test_all_parsers_have_ping_template(self):
        for device_type, parser in PARSERS.items():
            assert parser.ping_command_template is not None
            assert '{dest}' in parser.ping_command_template
            assert '{src}' in parser.ping_command_template
    
    def test_all_parsers_have_parse_ospf(self):
        for device_type, parser in PARSERS.items():
            assert hasattr(parser, 'parse_ospf')
            assert callable(parser.parse_ospf)
    
    def test_all_parsers_have_parse_ping(self):
        for device_type, parser in PARSERS.items():
            assert hasattr(parser, 'parse_ping')
            assert callable(parser.parse_ping)
    
    def test_all_parsers_have_build_ping_command(self):
        for device_type, parser in PARSERS.items():
            cmd = parser.build_ping_command('10.0.0.1', '10.0.0.2')
            assert cmd is not None
            assert '10.0.0.1' in cmd
            assert '10.0.0.2' in cmd

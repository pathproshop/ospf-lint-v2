"""
Unit tests for Cisco IOS-XR parser.

Test data is based on real device outputs.
"""

import pytest
from parsers.ios_xr import IOSXRParser


# =============================================================================
# SAMPLE OUTPUTS (from real devices)
# =============================================================================

SAMPLE_OSPF_OUTPUT = """
Bundle-Ether1 is up, line protocol is up
  Internet Address 50.50.0.7/31, Area 0, SID 0, Strict-SPF SID 0
  Label stack Primary label 0 Backup label 0 SRTE label 0
  Process ID 19290, Router ID 50.50.0.2, Network Type POINT_TO_POINT, Cost: 1
  Transmit Delay is 1 sec, State POINT_TO_POINT, MTU 9202, MaxPktSz 9170
  Forward reference No, Unnumbered no,  Bandwidth 10000000
  Timer intervals configured, Hello 10, Dead 40, Wait 40, Retransmit 5
  Hello due in 00:00:03:055
  Index 1/1, flood queue length 0
  Next 0(0)/0(0)
  Last flood scan length is 1, maximum is 5
  Last flood scan time is 0 msec, maximum is 0 msec
  LS Ack List: current length 0, high water mark 1
  Neighbor Count is 1, Adjacent neighbor count is 1
    Adjacent with neighbor 50.50.0.1
  Suppress hello for 0 neighbor(s)
  Multi-area interface Count is 0
Bundle-Ether2 is up, line protocol is up
  Internet Address 50.50.0.9/31, Area 0, SID 0, Strict-SPF SID 0
  Label stack Primary label 0 Backup label 0 SRTE label 0
  Process ID 19290, Router ID 50.50.0.2, Network Type POINT_TO_POINT, Cost: 20
  Transmit Delay is 1 sec, State POINT_TO_POINT, MTU 9202, MaxPktSz 9170
  Neighbor Count is 1, Adjacent neighbor count is 1
    Adjacent with neighbor 50.50.0.3
Bundle-Ether4 is up, line protocol is up
  Internet Address 66.181.248.29/31, Area 0, SID 0, Strict-SPF SID 0
  Process ID 19290, Router ID 50.50.0.2, Network Type POINT_TO_POINT, Cost: 20000
  Transmit Delay is 1 sec, State POINT_TO_POINT, MTU 9178, MaxPktSz 9170
  Neighbor Count is 1, Adjacent neighbor count is 1
Loopback0 is up, line protocol is up
  Internet Address 50.50.0.2/32, Area 0, SID 0, Strict-SPF SID 0
  Process ID 19290, Router ID 50.50.0.2, Network Type LOOPBACK, Cost: 1
Null0 is up, line protocol is up
  Process ID 19290, Router ID 50.50.0.2, Network Type POINT_TO_POINT, Cost: 1
"""

SAMPLE_DESC_OUTPUT = """
Interface          Status      Protocol    Description
--------------------------------------------------------------------------------
Lo0                up          up          
Nu0                up          up          
BE1                up          up          type=core,subtype=local,cid=CIDXXXXXXX,peer=cr1-iad5,peerint=be1
BE2                up          up          type=core,subtype=longhaul,cid=CIDXXXXXXX,peer=cr1-dfw2,peerint=be2
BE4                up          up          type=core,subtype=metro,peer=iad1er02,peerint=ae5.0
"""

SAMPLE_PING_OUTPUT = """
Tue Dec 30 22:37:04.907 UTC
Type escape sequence to abort.
Sending 100, 100-byte ICMP Echos to 50.50.0.11, timeout is 2 seconds:
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Success rate is 100 percent (100/100), round-trip min/avg/max = 1/2/9 ms
"""

SAMPLE_PING_OUTPUT_PARTIAL = """
Tue Dec 30 22:37:05.003 UTC
Type escape sequence to abort.
Sending 100, 100-byte ICMP Echos to 50.50.0.6, timeout is 2 seconds:
!!!!!!.!!!!!!.!!!!!!!!!!!!.!!!!!!!!!!!!!.!!.!!!!!!!!!!!.!!!!!!!!!!!!!!
!.!!!!!!!!!!!!!!!!!!!!!!!!.!!!
Success rate is 92 percent (92/100), round-trip min/avg/max = 1/2/8 ms
"""


# =============================================================================
# PARSER ATTRIBUTE TESTS
# =============================================================================

class TestIOSXRParserAttributes:
    """Test parser class attributes."""
    
    def test_device_type(self):
        assert IOSXRParser.device_type == 'cisco_xr'
    
    def test_ospf_commands(self):
        assert 'show ospf interface' in IOSXRParser.ospf_commands
        assert 'show interfaces description' in IOSXRParser.ospf_commands
    
    def test_ping_command_template(self):
        assert IOSXRParser.ping_command_template is not None
        assert '{dest}' in IOSXRParser.ping_command_template
        assert '{src}' in IOSXRParser.ping_command_template
        # XR doesn't use 'rapid'
        assert 'rapid' not in IOSXRParser.ping_command_template


# =============================================================================
# OSPF PARSING TESTS
# =============================================================================

class TestIOSXRParseOSPF:
    """Test OSPF output parsing."""
    
    def test_parse_ospf_returns_list(self):
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        assert isinstance(results, list)
    
    def test_parse_ospf_correct_count(self):
        """Should return 3 interfaces (BE1, BE2, BE4) - excludes loopback and null."""
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        assert len(results) == 3
    
    def test_parse_ospf_interface_fields(self):
        results = IOSXRParser.parse_ospf('cr2-iad5', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        
        # Find Bundle-Ether1
        be1 = next((r for r in results if r['interface'] == 'Bundle-Ether1'), None)
        assert be1 is not None
        assert be1['host'] == 'cr2-iad5'
        assert be1['ip'] == '50.50.0.7'
        assert be1['mask'] == '255.255.255.254'  # /31 converted
        assert be1['mtu'] == '9202'
        assert be1['cost'] == '1'
    
    def test_parse_ospf_description_lookup(self):
        """Should match description using shortened interface name."""
        results = IOSXRParser.parse_ospf('cr2-iad5', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        
        be1 = next((r for r in results if r['interface'] == 'Bundle-Ether1'), None)
        assert be1 is not None
        assert 'type=core' in be1['description']
        assert 'peer=cr1-iad5' in be1['description']
    
    def test_parse_ospf_excludes_loopback(self):
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        interfaces = [r['interface'].lower() for r in results]
        assert not any('loopback' in i for i in interfaces)
    
    def test_parse_ospf_excludes_null(self):
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        interfaces = [r['interface'].lower() for r in results]
        assert not any('null' in i for i in interfaces)
    
    def test_parse_ospf_high_cost(self):
        """Should correctly parse high cost values like 20000."""
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        
        be4 = next((r for r in results if r['interface'] == 'Bundle-Ether4'), None)
        assert be4 is not None
        assert be4['cost'] == '20000'
    
    def test_parse_ospf_empty_inputs(self):
        results = IOSXRParser.parse_ospf('testhost', {
            'show ospf interface': '',
            'show interfaces description': '',
        })
        assert results == []


# =============================================================================
# PING PARSING TESTS
# =============================================================================

class TestIOSXRParsePing:
    """Test ping output parsing."""
    
    def test_parse_ping_extracts_min_rtt(self):
        result = IOSXRParser.parse_ping(SAMPLE_PING_OUTPUT)
        assert result == '1'
    
    def test_parse_ping_with_drops(self):
        """Should still parse min RTT even with packet loss."""
        result = IOSXRParser.parse_ping(SAMPLE_PING_OUTPUT_PARTIAL)
        assert result == '1'
    
    def test_parse_ping_invalid_output(self):
        result = IOSXRParser.parse_ping("some garbage output")
        assert result is None
    
    def test_parse_ping_empty_output(self):
        result = IOSXRParser.parse_ping("")
        assert result is None


# =============================================================================
# INTERFACE NAME SHORTENING TESTS
# =============================================================================

class TestIOSXRInterfaceShortening:
    """Test interface name conversion."""
    
    def test_shorten_bundle_ether(self):
        assert IOSXRParser._shorten_interface_name('Bundle-Ether1') == 'BE1'
        assert IOSXRParser._shorten_interface_name('Bundle-Ether10') == 'BE10'
        assert IOSXRParser._shorten_interface_name('Bundle-Ether1.100') == 'BE1.100'
    
    def test_shorten_tengig(self):
        assert IOSXRParser._shorten_interface_name('TenGigE0/0/0/1') == 'Te0/0/0/1'
        assert IOSXRParser._shorten_interface_name('TenGigabitEthernet0/0/0/1') == 'Te0/0/0/1'
    
    def test_shorten_hundredgig(self):
        assert IOSXRParser._shorten_interface_name('HundredGigE0/0/0/1') == 'Hu0/0/0/1'
    
    def test_shorten_unknown_passthrough(self):
        assert IOSXRParser._shorten_interface_name('SomeWeirdInterface') == 'SomeWeirdInterface'


# =============================================================================
# PING COMMAND BUILDER TESTS
# =============================================================================

class TestIOSXRBuildPingCommand:
    """Test ping command generation."""
    
    def test_build_ping_command(self):
        cmd = IOSXRParser.build_ping_command('10.0.0.1', '10.0.0.2')
        assert cmd == 'ping 10.0.0.1 source 10.0.0.2 count 100'
    
    def test_build_ping_command_no_rapid(self):
        cmd = IOSXRParser.build_ping_command('10.0.0.1', '10.0.0.2')
        assert 'rapid' not in cmd

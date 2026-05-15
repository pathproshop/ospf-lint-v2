"""
Unit tests for Cisco IOS parser.

Test data is based on real device outputs.
"""

import pytest
from parsers.ios import IOSParser


# =============================================================================
# SAMPLE OUTPUTS (from real devices)
# =============================================================================

SAMPLE_OSPF_OUTPUT = """
Loopback0 is up, line protocol is up 
  Internet Address 50.50.0.14/32, Interface ID 12, Area 0.0.0.0
  Attached via Interface Enable
  Process ID 19290, Router ID 50.50.0.14, Network Type LOOPBACK, Cost: 1
  Topology-MTID    Cost    Disabled    Shutdown      Topology Name
        0           1         no          no            Base
  Enabled by interface config, including secondary ip addresses
  Loopback interface is treated as a stub Host
Port-channel2 is up, line protocol is up 
  Internet Address 50.50.0.19/31, Interface ID 14, Area 0.0.0.0
  Attached via Interface Enable
  Process ID 19290, Router ID 50.50.0.14, Network Type POINT_TO_POINT, Cost: 29
  Topology-MTID    Cost    Disabled    Shutdown      Topology Name
        0           29        no          no            Base
  Enabled by interface config, including secondary ip addresses
  Transmit Delay is 1 sec, State POINT_TO_POINT
  Timer intervals configured, Hello 10, Dead 40, Wait 40, Retransmit 5
    oob-resync timeout 40
    Hello due in 00:00:02
  Supports Link-local Signaling (LLS)
  Cisco NSF helper support enabled
  IETF NSF helper support enabled
  Neighbor Count is 1, Adjacent neighbor count is 1 
    Adjacent with neighbor 50.50.0.2
  Suppress hello for 0 neighbor(s)
Port-channel1 is up, line protocol is up 
  Internet Address 50.50.0.17/31, Interface ID 13, Area 0.0.0.0
  Attached via Interface Enable
  Process ID 19290, Router ID 50.50.0.14, Network Type POINT_TO_POINT, Cost: 10
  Topology-MTID    Cost    Disabled    Shutdown      Topology Name
        0           10        no          no            Base
  Enabled by interface config, including secondary ip addresses
  Transmit Delay is 1 sec, State POINT_TO_POINT
  Neighbor Count is 1, Adjacent neighbor count is 1 
    Adjacent with neighbor 50.50.0.1
  Suppress hello for 0 neighbor(s)
"""

SAMPLE_DESC_OUTPUT = """
Interface                      Status         Protocol Description
Gi1                            admin down     down     
Gi2                            admin down     down     
Gi3                            up             up       type=core,subtype=longhaul,lag=po1,peer=cr2-dfw2,peerint=gi0/0/0/2
Gi4                            up             up       type=core,subtype=longhaul,lag=po2,peer=cr1-iad1,peerint=gi0/0/0/2
Lo0                            up             up       
Po1                            up             up       type=core,subtype=longhaul,cid=CIDXXXXXXX,peer=cr2-dfw2,peerint=be4
Po2                            up             up       type=core,subtype=longhaul,cid=CIDXXXXXXX,peer=cr1-iad5,peerint=be4
"""

SAMPLE_INTF_OUTPUT = """
Port-channel1 is up, line protocol is up 
  Hardware is GEChannel, address is 001e.49bb.bcc0 (bia 001e.49bb.bcc0)
  Description: type=core,subtype=longhaul,cid=CIDXXXXXXX,peer=cr2-dfw2,peerint=be4
  Internet address is 50.50.0.17/31
  MTU 9202 bytes, BW 1000000 Kbit/sec, DLY 10 usec, 
     reliability 255/255, txload 1/255, rxload 1/255
  Encapsulation ARPA, loopback not set
Port-channel2 is up, line protocol is up 
  Hardware is GEChannel, address is 001e.49bb.bcc1 (bia 001e.49bb.bcc1)
  Description: type=core,subtype=longhaul,cid=CIDXXXXXXX,peer=cr1-iad5,peerint=be4
  Internet address is 50.50.0.19/31
  MTU 9202 bytes, BW 1000000 Kbit/sec, DLY 10 usec, 
     reliability 255/255, txload 1/255, rxload 1/255
  Encapsulation ARPA, loopback not set
"""

SAMPLE_PING_OUTPUT = """
Type escape sequence to abort.
Sending 100, 100-byte ICMP Echos to 50.50.0.16, timeout is 2 seconds:
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Success rate is 100 percent (100/100), round-trip min/avg/max = 1/2/8 ms
"""


# =============================================================================
# PARSER ATTRIBUTE TESTS
# =============================================================================

class TestIOSParserAttributes:
    """Test parser class attributes."""
    
    def test_device_type(self):
        assert IOSParser.device_type == 'cisco_ios'
    
    def test_ospf_commands(self):
        assert 'show ip ospf interface' in IOSParser.ospf_commands
        assert 'show interfaces description' in IOSParser.ospf_commands
        assert 'show interfaces' in IOSParser.ospf_commands
    
    def test_ping_command_template(self):
        assert IOSParser.ping_command_template is not None
        assert '{dest}' in IOSParser.ping_command_template
        assert '{src}' in IOSParser.ping_command_template
        assert 'repeat' in IOSParser.ping_command_template


# =============================================================================
# OSPF PARSING TESTS
# =============================================================================

class TestIOSParseOSPF:
    """Test OSPF output parsing."""
    
    def test_parse_ospf_returns_list(self):
        results = IOSParser.parse_ospf('testhost', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        assert isinstance(results, list)
    
    def test_parse_ospf_correct_count(self):
        """Should return 2 interfaces (Po1, Po2) - excludes loopback."""
        results = IOSParser.parse_ospf('testhost', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        assert len(results) == 2
    
    def test_parse_ospf_interface_fields(self):
        results = IOSParser.parse_ospf('er1-iah1', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        
        # Find Port-channel1
        po1 = next((r for r in results if r['interface'] == 'Port-channel1'), None)
        assert po1 is not None
        assert po1['host'] == 'er1-iah1'
        assert po1['ip'] == '50.50.0.17'
        assert po1['mask'] == '255.255.255.254'  # /31 converted
        assert po1['cost'] == '10'
    
    def test_parse_ospf_mtu_from_show_interfaces(self):
        """Should get MTU from 'show interfaces' output."""
        results = IOSParser.parse_ospf('er1-iah1', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        
        po1 = next((r for r in results if r['interface'] == 'Port-channel1'), None)
        assert po1 is not None
        assert po1['mtu'] == '9202'
    
    def test_parse_ospf_description_lookup(self):
        """Should match description using shortened interface name (Port-channel1 -> Po1)."""
        results = IOSParser.parse_ospf('er1-iah1', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        
        po1 = next((r for r in results if r['interface'] == 'Port-channel1'), None)
        assert po1 is not None
        assert 'type=core' in po1['description']
        assert 'peer=cr2-dfw2' in po1['description']
    
    def test_parse_ospf_excludes_loopback(self):
        results = IOSParser.parse_ospf('testhost', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
            'show interfaces': SAMPLE_INTF_OUTPUT,
        })
        interfaces = [r['interface'].lower() for r in results]
        assert not any('loopback' in i for i in interfaces)
    
    def test_parse_ospf_without_show_interfaces(self):
        """Should still work without 'show interfaces' (just missing MTU)."""
        results = IOSParser.parse_ospf('er1-iah1', {
            'show ip ospf interface': SAMPLE_OSPF_OUTPUT,
            'show interfaces description': SAMPLE_DESC_OUTPUT,
        })
        
        assert len(results) == 2
        po1 = next((r for r in results if r['interface'] == 'Port-channel1'), None)
        assert po1 is not None
        assert po1['mtu'] == ''  # No MTU without show interfaces
    
    def test_parse_ospf_empty_inputs(self):
        results = IOSParser.parse_ospf('testhost', {
            'show ip ospf interface': '',
            'show interfaces description': '',
        })
        assert results == []


# =============================================================================
# PING PARSING TESTS
# =============================================================================

class TestIOSParsePing:
    """Test ping output parsing."""
    
    def test_parse_ping_extracts_min_rtt(self):
        result = IOSParser.parse_ping(SAMPLE_PING_OUTPUT)
        assert result == '1'
    
    def test_parse_ping_invalid_output(self):
        result = IOSParser.parse_ping("some garbage output")
        assert result is None
    
    def test_parse_ping_empty_output(self):
        result = IOSParser.parse_ping("")
        assert result is None


# =============================================================================
# INTERFACE NAME SHORTENING TESTS
# =============================================================================

class TestIOSInterfaceShortening:
    """Test interface name conversion."""
    
    def test_shorten_port_channel(self):
        assert IOSParser._shorten_interface_name('Port-channel1') == 'Po1'
        assert IOSParser._shorten_interface_name('Port-channel10') == 'Po10'
    
    def test_shorten_gigabit(self):
        assert IOSParser._shorten_interface_name('GigabitEthernet0/0') == 'Gi0/0'
        assert IOSParser._shorten_interface_name('GigabitEthernet1/0/1') == 'Gi1/0/1'
    
    def test_shorten_tengig(self):
        assert IOSParser._shorten_interface_name('TenGigabitEthernet1/0/1') == 'Te1/0/1'
    
    def test_shorten_loopback(self):
        assert IOSParser._shorten_interface_name('Loopback0') == 'Lo0'
    
    def test_shorten_vlan(self):
        assert IOSParser._shorten_interface_name('Vlan100') == 'Vl100'
    
    def test_shorten_unknown_passthrough(self):
        assert IOSParser._shorten_interface_name('SomeWeirdInterface') == 'SomeWeirdInterface'


# =============================================================================
# PING COMMAND BUILDER TESTS
# =============================================================================

class TestIOSBuildPingCommand:
    """Test ping command generation."""
    
    def test_build_ping_command(self):
        cmd = IOSParser.build_ping_command('10.0.0.1', '10.0.0.2')
        assert cmd == 'ping 10.0.0.1 source 10.0.0.2 repeat 100'
    
    def test_build_ping_command_uses_repeat(self):
        """IOS uses 'repeat' not 'count'."""
        cmd = IOSParser.build_ping_command('10.0.0.1', '10.0.0.2')
        assert 'repeat' in cmd
        assert 'count' not in cmd

"""
Cisco IOS OSPF parser plugin.
"""

import re
import ipaddress
from .base import OSPFParser


class IOSParser(OSPFParser):
    """Parser for Cisco IOS devices."""
    
    device_type = 'cisco_ios'
    
    ospf_commands = [
        'show ip ospf interface',
        'show interfaces description',
        'show interfaces',
    ]
    
    ping_command_template = "ping {dest} source {src} repeat 100"
    
    @classmethod
    def _mask_from_prefix(cls, prefix):
        """Convert prefix length to dotted-decimal mask."""
        try:
            return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        except Exception:
            return ''
    
    @classmethod
    def _shorten_interface_name(cls, iface):
        """Convert IOS long interface names to short form for description lookup."""
        patterns = [
            (r'^Port-channel(\d+)$', 'Po'),
            (r'^GigabitEthernet(\d+(/\d+)*)$', 'Gi'),
            (r'^TenGigabitEthernet(\d+(/\d+)*)$', 'Te'),
            (r'^FastEthernet(\d+(/\d+)*)$', 'Fa'),
            (r'^Ethernet(\d+(/\d+)*)$', 'Et'),
            (r'^Loopback(\d+)$', 'Lo'),
            (r'^Vlan(\d+)$', 'Vl'),
            (r'^Tunnel(\d+)$', 'Tu'),
        ]
        
        for pattern, prefix in patterns:
            m = re.match(pattern, iface, re.IGNORECASE)
            if m:
                return prefix + m.group(1)
        
        return iface
    
    @classmethod
    def parse_ospf(cls, host, command_outputs):
        """Parse IOS OSPF, interface description, and interface outputs."""
        ospf_output = command_outputs.get('show ip ospf interface', '')
        desc_output = command_outputs.get('show interfaces description', '')
        intf_output = command_outputs.get('show interfaces', '')
        
        if not ospf_output or not desc_output:
            return []
        
        # Build description lookup from 'show interfaces description'
        desc_dict = {}
        for line in desc_output.splitlines():
            line = line.strip()
            if not line or line.startswith('Interface') or line.startswith('-'):
                continue
            m = re.match(r'^(\S+)\s+(up|down|admin down|administratively down)\s+(up|down)\s*(.*)', line, re.IGNORECASE)
            if m:
                iface_short = m.group(1)
                desc = m.group(4).strip()
                desc_dict[iface_short] = desc
        
        # Build MTU lookup from 'show interfaces' if provided
        mtu_dict = {}
        if intf_output:
            intf_blocks = re.split(r'\n(?=\S+\s+is\s+(?:up|down|administratively down))', intf_output)
            for block in intf_blocks:
                iface_match = re.match(r'^(\S+)\s+is\s+', block)
                if iface_match:
                    iface_name = iface_match.group(1)
                    mtu_match = re.search(r'MTU\s+(\d+)\s+bytes', block)
                    if mtu_match:
                        mtu_dict[iface_name] = mtu_match.group(1)
                        mtu_dict[cls._shorten_interface_name(iface_name)] = mtu_match.group(1)
        
        results = []
        blocks = re.split(r'\n(?=\S+\s+is\s+(?:up|down|administratively down),\s+line protocol is)', ospf_output)
        
        for block in blocks:
            # Skip loopbacks and passive interfaces
            if "treated as a stub Host" in block:
                continue
            if "No Hellos (Passive interface)" in block:
                continue
            
            m = re.match(r'^(\S+)\s+is\s+(?:up|down|administratively down),\s+line protocol is\s+(?:up|down)', block.strip())
            if not m:
                continue
            
            iface = m.group(1)
            if iface.lower().startswith('loopback'):
                continue
            
            ip = mask = cost = mtu = ''
            
            # Parse IP address
            ip_match = re.search(r'Internet Address\s+([\d\.]+)/(\d+)', block)
            if ip_match:
                ip = ip_match.group(1)
                mask = cls._mask_from_prefix(ip_match.group(2))
            
            # Parse cost
            cost_match = re.search(r'Cost:\s*(\d+)', block)
            if cost_match:
                cost = cost_match.group(1)
            
            # Get short interface name for lookups
            iface_short = cls._shorten_interface_name(iface)
            
            # Lookup description using short name
            desc = desc_dict.get(iface_short, '')
            
            # Lookup MTU
            mtu = mtu_dict.get(iface, '') or mtu_dict.get(iface_short, '')
            
            results.append({
                'host': host,
                'interface': iface,
                'mtu': mtu,
                'ip': ip,
                'mask': mask,
                'cost': cost,
                'description': desc
            })
        
        return results
    
    @classmethod
    def parse_ping(cls, output):
        """Parse IOS ping output for min RTT."""
        # Success rate is 100 percent (100/100), round-trip min/avg/max = 1/1/4 ms
        match = re.search(r'round-trip min/avg/max\s*=\s*([\d\.]+)/', output)
        if match:
            return match.group(1)
        return None

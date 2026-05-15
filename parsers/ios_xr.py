"""
Cisco IOS-XR OSPF parser plugin.
"""

import re
import ipaddress
from .base import OSPFParser


class IOSXRParser(OSPFParser):
    """Parser for Cisco IOS-XR devices."""
    
    device_type = 'cisco_xr'
    
    ospf_commands = [
        'show ospf interface',
        'show interfaces description',
    ]
    
    ping_command_template = "ping {dest} source {src} count 100"
    
    @classmethod
    def _mask_from_prefix(cls, prefix):
        """Convert prefix length to dotted-decimal mask."""
        try:
            return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        except Exception:
            return ''
    
    @classmethod
    def _shorten_interface_name(cls, iface):
        """Convert IOS-XR long interface names to short form for description lookup."""
        patterns = [
            (r'Bundle-Ether(\d+(\.\d+)?)', 'BE'),
            (r'TenGigabitEthernet(\d+/\d+/\d+/\d+(\.\d+)?)', 'Te'),
            (r'TenGigE(\d+/\d+/\d+/\d+(\.\d+)?)', 'Te'),
            (r'HundredGigE(\d+/\d+/\d+/\d+(\.\d+)?)', 'Hu'),
            (r'HundredGigabitEthernet(\d+/\d+/\d+/\d+(\.\d+)?)', 'Hu'),
            (r'GigabitEthernet(\d+/\d+/\d+/\d+(\.\d+)?)', 'Gi'),
            (r'FastEthernet(\d+/\d+/\d+/\d+(\.\d+)?)', 'Fa'),
        ]
        
        for pattern, prefix in patterns:
            m = re.match(pattern, iface)
            if m:
                return prefix + m.group(1)
        
        return iface
    
    @classmethod
    def parse_ospf(cls, host, command_outputs):
        """Parse IOS-XR OSPF and interface description outputs."""
        ospf_output = command_outputs.get('show ospf interface', '')
        desc_output = command_outputs.get('show interfaces description', '')
        
        if not ospf_output or not desc_output:
            return []
        
        # Build description lookup
        desc_dict = {}
        for line in desc_output.splitlines():
            if line.strip().startswith('Interface') or line.strip().startswith('-') or not line.strip():
                continue
            m = re.match(r'^(\S+)\s+\S+\s+\S+\s+(.*)', line)
            if m:
                desc_dict[m.group(1)] = m.group(2).strip()
        
        results = []
        blocks = re.split(r'\n(?=[A-Za-z]+\S*\s+is up, line protocol is up)', ospf_output)
        
        for block in blocks:
            if "Passive interface" in block:
                continue
            
            m = re.match(r'^([A-Za-z0-9\-/\.]+) is up, line protocol is up', block.strip())
            if not m:
                continue
            
            iface = m.group(1)
            if iface.lower().startswith('lo') or iface.lower().startswith('nu'):
                continue
            
            mtu = ip = mask = cost = ''
            
            mtu_match = re.search(r'MTU\s+(\d+)', block)
            if mtu_match:
                mtu = mtu_match.group(1)
            
            ip_match = re.search(r'Internet Address\s+([\d\.]+)\/(\d+)', block)
            if ip_match:
                ip = ip_match.group(1)
                mask = cls._mask_from_prefix(ip_match.group(2))
            
            cost_match = re.search(r'Cost:\s*(\d+)', block)
            if cost_match:
                cost = cost_match.group(1)
            
            desc = desc_dict.get(cls._shorten_interface_name(iface), '')
            
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
        """Parse IOS-XR ping output for min RTT."""
        # round-trip min/avg/max = 1/1/2 ms (note: no stddev)
        match = re.search(r'round-trip min/avg/max\s*=\s*([\d\.]+)/', output)
        if match:
            return match.group(1)
        return None

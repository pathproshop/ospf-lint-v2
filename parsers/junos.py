"""
Juniper Junos OSPF parser plugin.
"""

import re
from .base import OSPFParser


class JunosParser(OSPFParser):
    """Parser for Juniper Junos devices."""
    
    device_type = 'juniper_junos'
    
    ospf_commands = [
        'show ospf interface detail',
        'show interfaces descriptions',
    ]
    
    ping_command_template = "ping {dest} source {src} rapid count 100"
    
    @classmethod
    def parse_ospf(cls, host, command_outputs):
        """Parse Junos OSPF and interface description outputs."""
        ospf_output = command_outputs.get('show ospf interface detail', '')
        desc_output = command_outputs.get('show interfaces descriptions', '')
        
        if not ospf_output or not desc_output:
            return []
        
        # Normalize newlines
        ospf_output = ospf_output.replace('\\n', '\n')
        desc_output = desc_output.replace('\\n', '\n')
        
        # Build description lookup
        desc_dict = {}
        for line in desc_output.splitlines():
            if line.strip().startswith('Interface') or line.strip().startswith('Admin') or not line.strip():
                continue
            m = re.match(r'^(\S+)\s+\S+\s+\S+\s+(.+)', line)
            if m:
                desc_dict[m.group(1)] = m.group(2)
        
        results = []
        blocks = re.split(r'\n(?=\S)', ospf_output)
        
        for block in blocks:
            # Skip passive interfaces
            if "Passive" in block:
                continue
            
            m = re.match(r'^(\S+)', block)
            if not m:
                continue
            
            iface = m.group(1).rstrip(',')  # Strip trailing comma
            
            # Skip loopbacks and other non-relevant interfaces
            if iface.lower().startswith('lo') or iface in ['{master}', 'Interface']:
                continue
            
            mtu = ip = mask = cost = ''
            
            mtu_match = re.search(r'MTU[:\s]+(\d+)', block)
            if mtu_match:
                mtu = mtu_match.group(1)
            
            ip_match = re.search(r'Address:\s*([\d\.]+),\s*Mask:\s*([\d\.]+)', block)
            if ip_match:
                ip = ip_match.group(1)
                mask = ip_match.group(2)
            
            cost_match = re.search(r'Cost:\s*(\d+)', block)
            if cost_match:
                cost = cost_match.group(1)
            
            desc = desc_dict.get(iface, '')
            # If no description and iface ends with '.0', try parent
            if not desc and iface.endswith('.0'):
                parent_iface = iface[:-2]
                desc = desc_dict.get(parent_iface, '')
            
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
        """Parse Junos ping output for min RTT."""
        # round-trip min/avg/max/stddev = 0.452/0.523/1.234/0.089 ms
        match = re.search(r'round-trip min/avg/max/stddev\s*=\s*([\d\.]+)/', output)
        if match:
            # Round to integer for consistency
            return str(round(float(match.group(1))))
        return None


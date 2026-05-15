"""
Base class for platform-specific OSPF parsers.

All parser plugins must inherit from OSPFParser and implement the required methods.
"""

from abc import ABC, abstractmethod


class OSPFParser(ABC):
    """
    Abstract base class for platform-specific OSPF parsers.
    
    To create a new parser:
    1. Create a new file in the parsers/ directory
    2. Create a class that inherits from OSPFParser
    3. Set the class attributes (name, device_type, ospf_commands, ping_command_template)
    4. Implement parse_ospf() and parse_ping() methods
    
    The parser will be auto-discovered and registered.
    """
    
    # Netmiko device type (e.g., 'juniper_junos', 'cisco_xr')
    device_type = None
    
    # Commands to run for OSPF data collection
    # List of command strings
    ospf_commands = []
    
    # Ping command template with {dest} and {src} placeholders
    # e.g., "ping {dest} source {src} rapid count 100"
    ping_command_template = None
    
    @classmethod
    @abstractmethod
    def parse_ospf(cls, host, command_outputs):
        """
        Parse OSPF command outputs and return interface data.
        
        Args:
            host: Device hostname
            command_outputs: Dict mapping command string -> output string
        
        Returns:
            List of dicts, each containing:
                - host: str
                - interface: str
                - ip: str
                - mask: str
                - mtu: str
                - cost: str
                - description: str
        """
        raise NotImplementedError
    
    @classmethod
    @abstractmethod
    def parse_ping(cls, output):
        """
        Parse ping output and return minimum RTT.
        
        Args:
            output: Raw ping command output string
        
        Returns:
            Latency as string (integer milliseconds), or None if parse failed
        """
        raise NotImplementedError
    
    @classmethod
    def build_ping_command(cls, dest_ip, source_ip):
        """
        Build ping command from template.
        
        Args:
            dest_ip: Destination IP address
            source_ip: Source IP address
        
        Returns:
            Formatted ping command string
        """
        if not cls.ping_command_template:
            return None
        return cls.ping_command_template.format(dest=dest_ip, src=source_ip)

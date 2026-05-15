"""
OSPF Parser Plugin Registry

Auto-discovers and registers all parser plugins in this directory.
Each parser must inherit from OSPFParser and define a device_type.
"""

import importlib
import pkgutil
from pathlib import Path

from .base import OSPFParser

# Registry mapping device_type -> parser class
PARSERS = {}


def _discover_parsers():
    """
    Auto-discover parser plugins in this package.
    
    Scans all modules in the parsers directory, finds classes that
    inherit from OSPFParser, and registers them by device_type.
    """
    package_dir = Path(__file__).parent
    
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name == 'base':
            continue
        
        try:
            module = importlib.import_module(f'.{module_info.name}', package=__name__)
            
            # Find all OSPFParser subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, OSPFParser) and 
                    attr is not OSPFParser and
                    attr.device_type is not None):
                    PARSERS[attr.device_type] = attr
        except Exception as e:
            print(f"[ Warning: Failed to load parser module {module_info.name}: {e} ]")


def get_parser(device_type):
    """
    Get parser class for a device type.
    
    Args:
        device_type: Netmiko device type string (e.g., 'juniper_junos')
    
    Returns:
        Parser class or None if not found
    """
    return PARSERS.get(device_type)


def get_supported_platforms():
    """
    Get list of supported device types.
    
    Returns:
        List of device type strings
    """
    return list(PARSERS.keys())


# Auto-discover parsers on module import
_discover_parsers()

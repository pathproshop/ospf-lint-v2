# OSPF Lint

OSPF Interface Metrics Collection and Validation Tool

Collects OSPF interface information from network devices, pairs interfaces by subnet, and measures latency between paired endpoints for topology validation and cost analysis.

## Features

- Collects OSPF interface data: IP, mask, MTU, cost, description
- Pairs interfaces by matching subnets across devices
- Measures round-trip latency between paired endpoints
- Outputs CSV files for analysis and validation
- Multi-threaded for fast collection across large networks
- **Pluggable parser architecture** - easily add support for new platforms

## Supported Platforms

- Juniper Junos (`juniper_junos`)
- Cisco IOS-XR (`cisco_xr`)
- Cisco IOS (`cisco_ios`)
- Brocade FastIron (`brocade_fastiron`) - coming soon

## Installation

```bash
# Clone the repository
git clone https://github.com/pathproshop/ospf-lint-v2.git
cd ospf-lint

# Install in a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### Basic Usage (Interactive)

```bash
# Using current username, prompt for password
ospf-lint -f devices.txt

# Specify username
ospf-lint -f devices.txt -l admin

# Single device
ospf-lint -d router1.example.com -y juniper_junos

# List supported platforms
ospf-lint --list-platforms
```

### Automated Usage (Cron/Scripts)

```bash
# Create .env file from template
cp .env.example .env
# Edit .env with your credentials

# Run with env file
ospf-lint -f devices.txt -e .env
```

### Options

```
-d, --devices      Comma-separated list of devices
-f, --device-file  Path to device list file (hostname,device_type per line)
-t, --threads      Number of threads, max 50 (default: 10)
-y, --device-type  Device type (required with -d)
-l, --login        Username for device login (default: current user)
-e, --env          Path to .env file with USERNAME and PASSWORD
--skip-ping        Skip latency measurement
--ping-only FILE   Run ping only using existing pairs CSV file
--debug            Enable debug output for ping parsing
--list-platforms   List supported platforms and exit
--help             Show help message
```

### Device File Format

```
# devices.txt - one device per line: hostname,netmiko_device_type
router1,juniper_junos
router2,juniper_junos
core1,cisco_xr
core2,cisco_xr
switch1,cisco_ios
```

## Output Files

### ospf_interfaces.csv

All OSPF interfaces collected from devices:

```csv
host,interface,ip,mask,mtu,cost,description
router1,ae0.4,10.0.0.1,255.255.255.254,9170,1,type=core,peer=router2
router2,ae0.4,10.0.0.2,255.255.255.254,9170,1,type=core,peer=router1
```

### ospf_pairs_by_subnet.csv

Paired interfaces with latency measurements:

```csv
a_host,a_interface,a_description,a_ip,a_mtu,a_cost,latency_ms,z_cost,z_mtu,z_ip,z_description,z_interface,z_host
router1,ae0.4,type=core,10.0.0.1,9170,1,1,1,9170,10.0.0.2,type=core,ae0.4,router2
```

## Adding New Platform Parsers

OSPF Lint uses a pluggable parser architecture. To add support for a new platform:

1. Create a new file in `parsers/` directory (e.g., `parsers/myplatform.py`)
2. Create a class that inherits from `OSPFParser`
3. Define the required attributes and implement the methods

```python
from .base import OSPFParser
import re

class MyPlatformParser(OSPFParser):
    device_type = 'my_platform'  # Netmiko device type
    
    ospf_commands = [
        'show ospf interface',
        'show interface description',
    ]
    
    ping_command_template = "ping {dest} source {src} count 100"
    
    @classmethod
    def parse_ospf(cls, host, command_outputs):
        # Parse command outputs, return list of interface dicts
        results = []
        # ... parsing logic ...
        return results
    
    @classmethod
    def parse_ping(cls, output):
        # Parse ping output, return latency string or None
        match = re.search(r'min/avg/max\s*=\s*([\d\.]+)/', output)
        return match.group(1) if match else None
```

The parser will be automatically discovered and registered when OSPF Lint starts.

## Use Cases

- **Cost Validation**: Compare actual latency against configured OSPF costs
- **MTU Mismatch Detection**: Identify interfaces with mismatched MTU settings
- **Documentation**: Generate current-state topology documentation
- **Change Validation**: Before/after comparison for maintenance windows

## Project Structure

```
ospf-lint/
├── ospf_lint.py          # Main CLI and orchestration
├── parsers/
│   ├── __init__.py       # Auto-discovery and registry
│   ├── base.py           # Base parser class
│   ├── junos.py          # Juniper Junos parser
│   ├── ios_xr.py         # Cisco IOS-XR parser
│   └── ios.py            # Cisco IOS parser
├── setup.py
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Author

CFF / PathProShop

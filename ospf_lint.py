#!/usr/bin/env python3
"""
OSPF Lint - OSPF Interface Metrics Collection and Validation Tool

Collects OSPF interface information (IP, MTU, cost, description) from network devices,
pairs interfaces by subnet, and measures latency between paired endpoints for
topology validation and cost analysis.

Supports pluggable parsers for different platforms.
"""

import os
import re
import csv
import sys
import signal
import getpass
import logging
import ipaddress
import warnings
from queue import Queue, Empty
from datetime import datetime
from threading import Lock, Thread

import paramiko
from netmiko import (
    ConnectHandler,
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)

from parsers import get_parser, get_supported_platforms, PARSERS

# Suppress paramiko warnings
warnings.filterwarnings(action='ignore', module='.*paramiko.*')

# Find path to program working directory
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
sys.path.append(DIR_PATH)

# Paramiko KEX and key preferences for legacy device compatibility
paramiko.Transport._preferred_kex = (
    'diffie-hellman-group14-sha1',
    'diffie-hellman-group-exchange-sha1',
    'diffie-hellman-group1-sha1',
    'diffie-hellman-group-exchange-sha256',
)

paramiko.Transport._preferred_keys = (
    'ssh-rsa',
    'ssh-dss',
    'ecdsa-sha2-nistp256',
    'ecdh-sha2-nistp256',
    'ecdsa-sha2-nistp384',
    'ecdsa-sha2-nistp512',
)

# Configure logging
logging.basicConfig(filename=os.path.join(DIR_PATH, 'netmiko.log'), level=logging.DEBUG)
logger = logging.getLogger("netmiko")

# Signal handlers for clean exit
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.SIG_DFL)

# Process ID for termination
PID = os.getpid()

# Thread-safe print lock
print_lock = Lock()


# =============================================================================
# GENERIC THREADED COMMAND RUNNER
# =============================================================================

def worker_thread(thread_id, job_queue, results_dict, results_lock, username, password):
    """
    Worker thread that pulls jobs from queue and executes commands on devices.
    
    Each job is a dict with:
        - host: device hostname/IP
        - device_type: netmiko device type
        - commands: list of commands to run
        - job_id: (optional) identifier for this job, defaults to host
    """
    while True:
        try:
            job = job_queue.get(timeout=1)
        except Empty:
            break
        
        host = job['host']
        device_type = job['device_type']
        commands = job['commands']
        job_id = job.get('job_id', host)
        
        device = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "conn_timeout": 120,
            "read_timeout_override": 120,
            "global_delay_factor": 10,
        }
        
        try:
            net_connect = ConnectHandler(**device)
            
            results = []
            for cmd in commands:
                try:
                    output = net_connect.send_command(cmd, read_timeout=60)
                    results.append({'cmd': cmd, 'output': output})
                except Exception as e:
                    with print_lock:
                        print(f"[ Thread {thread_id}: Command failed on {host}: {cmd} - {e} ]")
                    results.append({'cmd': cmd, 'output': '', 'error': str(e)})
            
            net_connect.disconnect()
            
            with results_lock:
                results_dict[job_id] = {
                    'host': host,
                    'platform': device_type,
                    'results': results
                }
            
        except NetmikoTimeoutException:
            with print_lock:
                print(f"\n[ Thread {thread_id}: ERROR: Connection to {host} timed out ]\n")
            with results_lock:
                results_dict[job_id] = {
                    'host': host,
                    'platform': device_type,
                    'results': [],
                    'error': 'timeout'
                }
        except NetmikoAuthenticationException:
            with print_lock:
                print(f"\n[ Thread {thread_id}: ERROR: Authentication failed for {host} ]\n")
            with results_lock:
                results_dict[job_id] = {
                    'host': host,
                    'platform': device_type,
                    'results': [],
                    'error': 'auth_failed'
                }
        except Exception as e:
            with print_lock:
                print(f"\n[ Thread {thread_id}: ERROR: {host} - {e} ]\n")
            with results_lock:
                results_dict[job_id] = {
                    'host': host,
                    'platform': device_type,
                    'results': [],
                    'error': str(e)
                }
        finally:
            job_queue.task_done()


def run_commands_threaded(jobs, username, password, max_threads=10):
    """
    Execute commands on multiple devices using threading.
    
    Args:
        jobs: list of job dicts
        username: SSH username
        password: SSH password
        max_threads: maximum concurrent connections (default 10)
    
    Returns:
        dict mapping job_id -> {host, platform, results: [{cmd, output}], error?}
    """
    if not jobs:
        return {}
    
    job_queue = Queue()
    results_dict = {}
    results_lock = Lock()
    
    for job in jobs:
        job_queue.put(job)
    
    num_threads = min(max_threads, len(jobs))
    
    threads = []
    for i in range(num_threads):
        t = Thread(
            target=worker_thread,
            args=(i, job_queue, results_dict, results_lock, username, password)
        )
        t.daemon = True
        t.start()
        threads.append(t)
    
    job_queue.join()
    
    return results_dict


# =============================================================================
# DEVICE FILE PARSING
# =============================================================================

def load_device_list(devices_cli, device_file, device_type_cli):
    """
    Load device list from CLI option or file.
    
    Returns: list of (hostname, device_type) tuples
    """
    if devices_cli:
        print("[ Devices specified as CLI option ]\n")
        try:
            dev_list = []
            for device in devices_cli.split(","):
                dev_list.append((device.strip(), device_type_cli))
            print(f"[ Devices: {dev_list} ]\n")
            return dev_list
        except Exception as e:
            print(f"[ Error parsing devices: {e} ]\n")
            return None
    
    elif device_file:
        print(f"[ Loading devices from file: {device_file} ]\n")
        try:
            dev_list = []
            with open(device_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        dev_list.append((parts[0].strip(), parts[1].strip()))
            print(f"[ Loaded {len(dev_list)} devices ]\n")
            return dev_list
        except Exception as e:
            print(f"[ Error loading device file: {e} ]\n")
            return None
    
    return None


# =============================================================================
# JOB BUILDERS (using parser plugins)
# =============================================================================

def build_ospf_jobs(device_list):
    """
    Build job list for OSPF interface collection using parser plugins.
    
    Args:
        device_list: list of (hostname, device_type) tuples
    
    Returns:
        list of job dicts for run_commands_threaded()
    """
    jobs = []
    
    for hostname, device_type in device_list:
        parser = get_parser(device_type)
        if not parser:
            print(f"[ Warning: No parser for device type '{device_type}' ({hostname}), skipping ]\n")
            continue
        
        jobs.append({
            'host': hostname,
            'device_type': device_type,
            'commands': parser.ospf_commands,
        })
    
    return jobs


def build_ping_jobs(pairs, platform_map):
    """
    Build job list for ping latency measurement using parser plugins.
    Consolidates all pings for the same host into a single job.
    
    Args:
        pairs: list of paired interface dicts
        platform_map: dict mapping hostname -> device_type
    
    Returns:
        tuple: (jobs list, ping_metadata dict mapping host -> list of {pair_idx, cmd})
    """
    # Group pings by host
    host_pings = {}
    
    for idx, pair in enumerate(pairs):
        a_host = pair['a_host']
        z_ip = pair.get('z_ip', '')
        a_ip = pair.get('a_ip', '')
        
        if not z_ip or not a_host:
            continue
        
        device_type = platform_map.get(a_host)
        parser = get_parser(device_type)
        if not parser or not parser.ping_command_template:
            continue
        
        if a_host not in host_pings:
            host_pings[a_host] = []
        
        host_pings[a_host].append({
            'pair_idx': idx,
            'z_ip': z_ip,
            'a_ip': a_ip,
        })
    
    # Build consolidated jobs
    jobs = []
    ping_metadata = {}
    
    for host, ping_list in host_pings.items():
        device_type = platform_map.get(host)
        parser = get_parser(device_type)
        commands = []
        metadata = []
        
        for ping_info in ping_list:
            cmd = parser.build_ping_command(ping_info['z_ip'], ping_info['a_ip'])
            if cmd:
                commands.append(cmd)
                metadata.append({
                    'pair_idx': ping_info['pair_idx'],
                    'cmd': cmd,
                })
        
        if commands:
            jobs.append({
                'host': host,
                'device_type': device_type,
                'commands': commands,
                'job_id': f"ping_{host}",
            })
            ping_metadata[host] = metadata
    
    return jobs, ping_metadata


# =============================================================================
# RESULT PROCESSING (using parser plugins)
# =============================================================================

def process_ospf_results(results):
    """
    Process OSPF collection results into interface list using parser plugins.
    
    Args:
        results: dict from run_commands_threaded()
    
    Returns:
        list of interface dicts
    """
    ospf_interface_list = []
    
    for job_id, device_data in results.items():
        host = device_data['host']
        platform = device_data['platform']
        
        if device_data.get('error'):
            print(f"[ Skipping {host} due to error: {device_data['error']} ]")
            continue
        
        parser = get_parser(platform)
        if not parser:
            print(f"[ No parser for platform {platform} ({host}) ]")
            continue
        
        # Build command output dict
        command_outputs = {}
        for result in device_data['results']:
            command_outputs[result['cmd']] = result['output']
        
        # Parse using plugin
        parsed = parser.parse_ospf(host, command_outputs)
        ospf_interface_list.extend(parsed)
    
    return ospf_interface_list


def parse_ping_results(ping_results, pairs, ping_metadata, platform_map, debug=False):
    """
    Parse ping results and add latency_ms to pairs using parser plugins.
    
    Args:
        ping_results: dict from run_commands_threaded()
        pairs: list of paired interface dicts
        ping_metadata: dict mapping host -> list of {pair_idx, cmd}
        platform_map: dict mapping hostname -> device_type
        debug: if True, print verbose output
    
    Returns:
        pairs list with latency_ms added
    """
    # Initialize all pairs with empty latency
    for pair in pairs:
        pair['latency_ms'] = ''
    
    for job_id, result in ping_results.items():
        if not job_id.startswith('ping_'):
            continue
        
        host = result.get('host', 'unknown')
        platform = result.get('platform', '')
        
        if debug:
            print(f"\n[ DEBUG: Processing job {job_id} from {host} ({platform}) ]")
        
        if result.get('error'):
            if debug:
                print(f"[ DEBUG: Error flag set: {result.get('error')} ]")
            for meta in ping_metadata.get(host, []):
                pairs[meta['pair_idx']]['latency_ms'] = 'error'
            continue
        
        parser = get_parser(platform)
        if not parser:
            if debug:
                print(f"[ DEBUG: No parser for platform {platform} ]")
            continue
        
        metadata = ping_metadata.get(host, [])
        
        for cmd_result in result.get('results', []):
            cmd = cmd_result.get('cmd', '')
            output = cmd_result.get('output', '')
            
            # Find which pair this command belongs to
            pair_idx = None
            for meta in metadata:
                if meta['cmd'] == cmd:
                    pair_idx = meta['pair_idx']
                    break
            
            if pair_idx is None:
                if debug:
                    print(f"[ DEBUG: Could not map command to pair: {cmd} ]")
                continue
            
            if debug:
                print(f"\n[ DEBUG: Processing ping for pair {pair_idx} ]")
                print(f"[ DEBUG: Command: {cmd} ]")
                print(f"[ DEBUG: Output length: {len(output)} chars ]")
                if output:
                    print(f"[ DEBUG: Output tail:\n{output[-500:]}\n]")
            
            if not output:
                if debug:
                    print(f"[ DEBUG: No ping output found ]")
                pairs[pair_idx]['latency_ms'] = 'no_output'
                continue
            
            # Parse using plugin
            latency = parser.parse_ping(output)
            if latency:
                pairs[pair_idx]['latency_ms'] = latency
                if debug:
                    print(f"[ DEBUG: Parsed latency: {latency} ]")
            else:
                pairs[pair_idx]['latency_ms'] = 'parse_error'
                if debug:
                    print(f"[ DEBUG: Parse failed ]")
    
    return pairs


# =============================================================================
# INTERFACE PAIRING
# =============================================================================

def ips_in_same_subnet(ip1, mask1, ip2, mask2):
    """Check if two IPs are in the same subnet."""
    try:
        net1 = ipaddress.IPv4Network(f"{ip1}/{mask1}", strict=False)
        net2 = ipaddress.IPv4Network(f"{ip2}/{mask2}", strict=False)
        return net1.network_address == net2.network_address and net1.netmask == net2.netmask
    except Exception:
        return False


def pair_interfaces_by_subnet(all_entries):
    """
    Pair interfaces that share the same subnet.
    
    Returns list of dicts with a_* and z_* fields for each end of the link.
    """
    paired = []
    used = set()
    
    for i, a in enumerate(all_entries):
        if i in used:
            continue
        
        z = None
        for j, b in enumerate(all_entries):
            if j == i or j in used or a['host'] == b['host']:
                continue
            if ips_in_same_subnet(a['ip'], a['mask'], b['ip'], b['mask']):
                z = b
                used.add(j)
                break
        
        row = {
            'a_host': a['host'],
            'a_interface': a['interface'],
            'a_ip': a['ip'],
            'a_description': a['description'],
            'a_mtu': a['mtu'],
            'a_cost': a['cost'],
            'z_cost': z['cost'] if z else '',
            'z_mtu': z['mtu'] if z else '',
            'z_ip': z['ip'] if z else '',
            'z_description': z['description'] if z else '',
            'z_interface': z['interface'] if z else '',
            'z_host': z['host'] if z else ''
        }
        paired.append(row)
        used.add(i)
    
    return paired


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_start_time():
    """Get script start time."""
    return datetime.now()


def end_execution(pid, starttime=None):
    """End execution gracefully."""
    if starttime:
        endtime = datetime.now()
        totaltime = endtime - starttime
        print(f"[ Endtime: {endtime} ]")
        print(f"[ Total execution time: {totaltime} ]\n")
    else:
        print("[ Exiting ]\n")
    print(f"[ Ending execution of Process ID: {pid} ]\n")
    os.kill(pid, signal.SIGINT)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main program entry point."""
    import click
    
    @click.command()
    @click.option('-d', '--devices', help="Comma-separated list of devices", default=None)
    @click.option('-f', '--device-file', help="Path to device list file (hostname,device_type per line)")
    @click.option('-t', '--threads', help="Number of threads (max 50)", default=10, type=int)
    @click.option('-y', '--device-type', help="Device type (required with -d)", default=None)
    @click.option('-l', '--login', 'login_user', help="Username for device login (default: current user)", default=None)
    @click.option('-e', '--env', 'env_file', help="Path to .env file with USERNAME and PASSWORD", default=None)
    @click.option('--skip-ping', is_flag=True, help="Skip latency measurement")
    @click.option('--ping-only', help="Run ping only using existing pairs CSV file")
    @click.option('--debug', is_flag=True, help="Enable debug output for ping parsing")
    @click.option('--list-platforms', is_flag=True, help="List supported platforms and exit")
    def cli(devices, device_file, threads, device_type, login_user, env_file, skip_ping, ping_only, debug, list_platforms):
        """
        OSPF Lint - OSPF Interface Metrics Collection Tool
        
        Collects OSPF interface data and measures link latency for topology validation.
        """
        # Handle --list-platforms
        if list_platforms:
            print("\nSupported platforms:")
            for platform in sorted(get_supported_platforms()):
                parser = get_parser(platform)
                print(f"  - {platform}")
                print(f"      Commands: {parser.ospf_commands}")
                print(f"      Ping: {parser.ping_command_template}")
            print()
            return
        
        print(f'\n[ Script start with Process ID: {PID} ]\n')
        print(f"[ Supported platforms: {', '.join(sorted(get_supported_platforms()))} ]\n")
        
        # Limit threads
        threads = min(threads, 50)
        
        # Get credentials
        username = None
        password = None
        
        if env_file:
            print(f"[ Loading credentials from {env_file} ]\n")
            if not os.path.exists(env_file):
                print(f"[ Error: env file not found: {env_file} ]")
                end_execution(PID, starttime=None)
            
            from dotenv import dotenv_values
            env_vars = dotenv_values(env_file)
            
            username = env_vars.get('USERNAME') or env_vars.get('OSPF_LINT_USERNAME')
            password = env_vars.get('PASSWORD') or env_vars.get('OSPF_LINT_PASSWORD')
            
            if not username or not password:
                print("[ Error: USERNAME and PASSWORD must be set in env file ]")
                print("[ Expected: USERNAME=xxx and PASSWORD=xxx (or OSPF_LINT_USERNAME/OSPF_LINT_PASSWORD) ]\n")
                end_execution(PID, starttime=None)
        else:
            username = login_user if login_user else getpass.getuser()
            print(f"Username: {username}")
            password = getpass.getpass()
        
        starttime = get_start_time()
        print(f"\n[ Starttime: {starttime} ]\n")
        
        # Handle ping-only mode
        if ping_only:
            print(f"[ Ping-only mode: loading pairs from {ping_only} ]\n")
            
            pairs = []
            with open(ping_only, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pairs.append(row)
            
            device_list = load_device_list(devices, device_file, device_type)
            if not device_list:
                print("[ Error: Device list required for platform mapping ]")
                end_execution(PID, starttime)
            
            platform_map = {host: dtype for host, dtype in device_list}
            
            print(f"[ Building ping jobs for {len(pairs)} pairs ]\n")
            ping_jobs, ping_metadata = build_ping_jobs(pairs, platform_map)
            print(f"[ Running {len(ping_jobs)} ping jobs ({len(pairs)} pings consolidated by host) with {threads} threads ]\n")
            
            ping_results = run_commands_threaded(ping_jobs, username, password, max_threads=threads)
            pairs = parse_ping_results(ping_results, pairs, ping_metadata, platform_map, debug=debug)
            
            output_file = ping_only.replace('.csv', '_with_latency.csv')
            fieldnames = ['a_host', 'a_interface', 'a_description', 'a_ip', 'a_mtu', 'a_cost',
                         'latency_ms', 'z_cost', 'z_mtu', 'z_ip', 'z_description', 'z_interface', 'z_host']
            
            with open(output_file, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in pairs:
                    writer.writerow(row)
            
            print(f"[ Wrote {output_file} ]\n")
            end_execution(PID, starttime)
        
        # Normal mode
        device_list = load_device_list(devices, device_file, device_type)
        if not device_list:
            print("[ Error: No devices specified. Use -d or -f option. ]")
            end_execution(PID, starttime)
        
        platform_map = {host: dtype for host, dtype in device_list}
        
        print(f"[ Building OSPF collection jobs ]\n")
        ospf_jobs = build_ospf_jobs(device_list)
        print(f"[ Running {len(ospf_jobs)} jobs with {threads} threads ]\n")
        
        ospf_results = run_commands_threaded(ospf_jobs, username, password, max_threads=threads)
        
        ospf_interface_list = process_ospf_results(ospf_results)
        print(f"[ Collected {len(ospf_interface_list)} OSPF interfaces ]\n")
        
        with open('ospf_interfaces.csv', 'w', newline='') as csvfile:
            fieldnames = ['host', 'interface', 'ip', 'mask', 'mtu', 'cost', 'description']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in ospf_interface_list:
                writer.writerow(row)
        print("[ Wrote ospf_interfaces.csv ]\n")
        
        pairs = pair_interfaces_by_subnet(ospf_interface_list)
        print(f"[ Paired {len(pairs)} interface pairs ]\n")
        
        if not skip_ping and pairs:
            import time
            print("[ Waiting 5 seconds for device SSH sessions to reset... ]\n")
            time.sleep(5)
            
            print("[ Starting latency measurement ]\n")
            ping_jobs, ping_metadata = build_ping_jobs(pairs, platform_map)
            print(f"[ Running {len(ping_jobs)} ping jobs ({len(pairs)} pings consolidated by host) ]\n")
            
            ping_results = run_commands_threaded(ping_jobs, username, password, max_threads=threads)
            pairs = parse_ping_results(ping_results, pairs, ping_metadata, platform_map, debug=debug)
        
        fieldnames = ['a_host', 'a_interface', 'a_description', 'a_ip', 'a_mtu', 'a_cost',
                     'latency_ms', 'z_cost', 'z_mtu', 'z_ip', 'z_description', 'z_interface', 'z_host']
        
        with open('ospf_pairs_by_subnet.csv', 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in pairs:
                writer.writerow(row)
        print("[ Wrote ospf_pairs_by_subnet.csv ]\n")
        
        end_execution(PID, starttime)
    
    cli()


if __name__ == '__main__':
    main()

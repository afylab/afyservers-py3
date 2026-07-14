#!/usr/bin/env python3
"""
DAC Test Runner

Usage:
    python run_test.py <test_name>
    python run_test.py --list

This script:
1. Checks if LabRAD manager is running, starts it if not
2. Checks if serial server is running, starts it if not
3. Checks if the Arduino DAC port is in the registry, updates it if not
4. Checks if dac_adc_giga server is running, starts it if not
5. Runs the specified test
"""

import sys
import os
import subprocess
import time
import argparse
import glob
import atexit
import signal
from pathlib import Path

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
AFYSERVERS_DIR = SCRIPT_DIR.parent
LOG_DIR = SCRIPT_DIR / "logs"
sys.path.insert(0, str(AFYSERVERS_DIR))

# LabRAD paths
LABRAD_PATH = "/Users/space/Downloads/scalabrad-0.8.3/bin/labrad"
SERIAL_SERVER_PATH = AFYSERVERS_DIR / "serial_server.py"
DAC_SERVER_PATH = AFYSERVERS_DIR / "dac_adc_giga.py"

# Registry path for DAC links
REGISTRY_PATH = ['', 'Servers', 'dac_adc_giga', 'Links']
DAC_LINK_NAME = 'dac_adc'  # Key name in registry

# Timeouts
LABRAD_START_TIMEOUT = 5
SERVER_START_TIMEOUT = 5

# Track background processes for cleanup
_background_processes = []


def find_arduino_port():
    """Find the Arduino Giga port by looking for 'Arduino' in port description."""
    from serial.tools import list_ports

    ports = list_ports.comports()
    for port in ports:
        # Check if 'Arduino' appears in the description or hardware ID
        if 'Arduino' in port.description or 'Arduino' in (port.manufacturer or ''):
            print(f"Found Arduino at: {port.device} ({port.description})")
            return port.device
        # Also check for common Arduino USB identifiers
        if port.vid == 0x2341:  # Arduino vendor ID
            print(f"Found Arduino (by VID) at: {port.device}")
            return port.device

    # Fallback: look for common macOS Arduino port names
    for port in ports:
        if 'usbmodem' in port.device.lower():
            print(f"Found potential Arduino at: {port.device} ({port.description})")
            return port.device

    return None


def is_labrad_running():
    """Check if LabRAD manager is running."""
    try:
        import labrad
        cxn = labrad.connect(timeout=2)
        cxn.disconnect()
        return True
    except:
        return False


def is_server_running(server_name):
    """Check if a specific LabRAD server is running."""
    try:
        import labrad
        cxn = labrad.connect(timeout=2)
        result = server_name in cxn.servers
        cxn.disconnect()
        return result
    except:
        return False


def get_serial_server_name():
    """Get the name of the serial server (includes node name)."""
    import socket
    hostname = socket.gethostname().replace('.local', '').replace('.', '_')
    return f"{hostname} Serial Server"


def ensure_log_dir():
    """Ensure log directory exists."""
    LOG_DIR.mkdir(exist_ok=True)


def cleanup_processes(kill_servers=False):
    """Cleanup background processes. Only kills servers if explicitly requested."""
    if not kill_servers:
        # Don't kill servers - they should keep running
        return

    for proc in _background_processes:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except:
            try:
                proc.kill()
            except:
                pass


def start_labrad():
    """Start the LabRAD manager in the background."""
    print("Starting LabRAD manager...", end=" ", flush=True)
    ensure_log_dir()

    log_file = open(LOG_DIR / "labrad.log", "w")

    proc = subprocess.Popen(
        [LABRAD_PATH],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(AFYSERVERS_DIR),
        start_new_session=True
    )
    _background_processes.append(proc)

    # Wait for LabRAD to start
    start_time = time.time()
    while time.time() - start_time < LABRAD_START_TIMEOUT:
        if is_labrad_running():
            print("started")
            return True
        time.sleep(0.3)

    print("timeout (check logs/labrad.log)")
    return False


def start_server(server_path, server_name, check_name=None):
    """Start a LabRAD server in the background."""
    print(f"Starting {server_name}...", end=" ", flush=True)
    ensure_log_dir()

    log_name = server_name.lower().replace(' ', '_').replace('/', '_')
    log_file = open(LOG_DIR / f"{log_name}.log", "w")

    proc = subprocess.Popen(
        ['uv', 'run', str(server_path)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(AFYSERVERS_DIR),
        start_new_session=True
    )
    _background_processes.append(proc)

    # Wait for server to start
    if check_name:
        start_time = time.time()
        while time.time() - start_time < SERVER_START_TIMEOUT:
            if is_server_running(check_name):
                print("started")
                return True
            time.sleep(0.3)
        print(f"timeout (check logs/{log_name}.log)")
    else:
        time.sleep(1.5)
        print("started")

    return True


def check_and_update_registry():
    """Check if Arduino port is in registry, update if needed. Returns True if registry was modified."""
    import labrad

    cxn = labrad.connect()
    reg = cxn.registry

    # Navigate to the Links directory
    reg.cd(REGISTRY_PATH, True)  # True creates the path if it doesn't exist

    dirs, keys = reg.dir()

    # Check if we have the dac_adc key
    if DAC_LINK_NAME in keys:
        current_value = reg.get(DAC_LINK_NAME)
        print(f"Current registry value for '{DAC_LINK_NAME}': {current_value}")

        # Check if the port still exists
        arduino_port = find_arduino_port()
        if arduino_port:
            ser_server, port = current_value
            if port == arduino_port:
                print("Registry is up to date")
                cxn.disconnect()
                return False
            else:
                print(f"Port changed from {port} to {arduino_port}")
        else:
            print("Warning: Could not find Arduino port")
            cxn.disconnect()
            return False
    else:
        print(f"No '{DAC_LINK_NAME}' key found in registry")

    # Need to update registry
    arduino_port = find_arduino_port()
    if not arduino_port:
        print("Error: Cannot find Arduino port to update registry")
        cxn.disconnect()
        return False

    # Get the serial server name
    serial_server_name = get_serial_server_name()

    # Set the registry value: (serial_server_name, port)
    new_value = (serial_server_name, arduino_port)
    print(f"Updating registry: '{DAC_LINK_NAME}' = {new_value}")
    reg.set(DAC_LINK_NAME, new_value)

    cxn.disconnect()
    return True


def restart_labrad():
    """Restart LabRAD manager and all servers."""
    print("\nRestarting LabRAD to apply registry changes...")

    # Kill all tracked background processes
    for proc in _background_processes:
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except:
            try:
                proc.kill()
            except:
                pass
    _background_processes.clear()

    # Kill any remaining labrad-related processes
    subprocess.run(['pkill', '-f', 'labrad'], capture_output=True)
    subprocess.run(['pkill', '-f', 'serial_server'], capture_output=True)
    subprocess.run(['pkill', '-f', 'dac_adc_giga'], capture_output=True)
    time.sleep(1)

    # Start fresh
    return start_labrad()


def list_tests():
    """List all available tests."""
    test_files = list(SCRIPT_DIR.glob("test_*.py"))

    if not test_files:
        print("No test files found in test_dac directory")
        return

    print("Available tests:")
    for f in sorted(test_files):
        name = f.stem  # filename without extension
        # Try to get docstring
        try:
            with open(f) as fp:
                content = fp.read()
                if '"""' in content:
                    docstring = content.split('"""')[1].split('\n')[0].strip()
                    print(f"  {name}: {docstring}")
                else:
                    print(f"  {name}")
        except:
            print(f"  {name}")


def run_test(test_name):
    """Run the specified test."""
    # Handle both "test_foo" and "foo" as input
    if not test_name.startswith("test_"):
        test_name = f"test_{test_name}"

    if not test_name.endswith(".py"):
        test_name = f"{test_name}.py"

    test_path = SCRIPT_DIR / test_name

    if not test_path.exists():
        print(f"Error: Test '{test_name}' not found at {test_path}")
        print("\nAvailable tests:")
        list_tests()
        return False

    print(f"\n{'='*60}")
    print(f"Running test: {test_name}")
    print(f"{'='*60}\n")

    # Run the test with uv
    result = subprocess.run(
        ['uv', 'run', str(test_path)],
        cwd=str(SCRIPT_DIR)
    )

    return result.returncode == 0


def ensure_servers_running():
    """Ensure all required servers are running."""

    # Step 1: Check/start LabRAD manager
    if not is_labrad_running():
        print("LabRAD manager is not running")
        if not start_labrad():
            print("Failed to start LabRAD manager")
            return False
        time.sleep(1)
    else:
        print("LabRAD manager is running")

    # Step 2: Check/start serial server
    serial_server_name = get_serial_server_name()
    if not is_server_running(serial_server_name):
        print(f"Serial server ({serial_server_name}) is not running")
        start_server(SERIAL_SERVER_PATH, "Serial Server", serial_server_name)
        time.sleep(1)
    else:
        print(f"Serial server is running")

    # Step 3: Check/update registry for Arduino port
    registry_modified = check_and_update_registry()

    # Step 4: If registry was modified, need to restart everything
    if registry_modified:
        print("\nRegistry was modified - restarting LabRAD...")
        restart_labrad()
        time.sleep(1)

        # Restart serial server
        start_server(SERIAL_SERVER_PATH, "Serial Server", serial_server_name)
        time.sleep(1)

    # Step 5: Check/start DAC server
    if not is_server_running('dac_adc_giga'):
        print("DAC/ADC server is not running")
        start_server(DAC_SERVER_PATH, "DAC ADC Giga", 'dac_adc_giga')
        time.sleep(2)
    else:
        print("DAC/ADC server is running")

    # Final verification
    if not is_server_running('dac_adc_giga'):
        print("Warning: DAC/ADC server may not have started properly")
        print("Please check the terminal windows for errors")
        return False

    print("\nAll servers are running!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='DAC Test Runner - manages LabRAD servers and runs tests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_test.py awg_trapezoid     # Run the AWG trapezoid test
    python run_test.py test_awg_simple   # Full test name also works
    python run_test.py --list            # List all available tests
    python run_test.py --servers-only    # Just start servers, don't run a test
        """
    )

    parser.add_argument('test', nargs='?', help='Name of the test to run (e.g., awg_trapezoid)')
    parser.add_argument('--list', '-l', action='store_true', help='List available tests')
    parser.add_argument('--servers-only', '-s', action='store_true', help='Only start servers, do not run a test')
    parser.add_argument('--skip-servers', action='store_true', help='Skip server checks (assume servers are running)')

    args = parser.parse_args()

    if args.list:
        list_tests()
        return 0

    if not args.servers_only and not args.test:
        parser.print_help()
        return 1

    # Ensure servers are running
    if not args.skip_servers:
        print("Checking LabRAD servers...\n")
        if not ensure_servers_running():
            print("\nFailed to start all required servers")
            return 1

    if args.servers_only:
        print("\nServers are ready!")
        return 0

    # Run the test
    success = run_test(args.test)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

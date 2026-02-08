# use Tak's gnome_modem.py or thanos.py to get cm ip or cpe ip address
# input parameters: arg1 = Prod or Dev (Preprod), arg2 = CM or CPE, arg3 = CM MAC list
# change thanos.py to thanos2.py due to url change
# V 2.2 based on v2.1 and added passing of Thanos API keys through the .env file

import subprocess
import json
import concurrent.futures
import ipaddress
import sys
import os

# --- Load environment variables from .env file ---
try:
    from dotenv import load_dotenv
    load_dotenv()  # Will search for .env in current and parent directories
except ImportError:
    print("Error loading .env file. No .env file found.")
    pass


def run_script_and_get_result(script_path, arguments=[]):
  """
  Runs a Python script in a subprocess and returns the output.

  Args:
    script_path: The path to the Python script to execute.
    arguments: A list of arguments to pass to the script.

  Returns:
    A string containing the output of the script, or None if an error occurred.
  """
  try:
    # Construct the command to execute
    command = ["python", script_path] + arguments 
    # Run the script using subprocess
    process = subprocess.run(command, capture_output=True, text=True)
    # Check for errors
    if process.returncode == 0:
      return process.stdout.strip()  # Return the output
    else:
      print(f"Error running script: {process.stderr}")
      return None

  except FileNotFoundError:
    print(f"Script not found: {script_path}")
    return None

def run_script(script_path, arguments=[]):
    """
    Runs a Python script in a subprocess.

    Args:
      script_path: The path to the Python script to execute.
      arguments: A list of arguments to pass to the script.
    """
    try:
        command = ["python", script_path] + arguments
        process = subprocess.run(command, capture_output=True, text=True)
        if not process.returncode == 0:
            print(f"Error running script {script_path}: {process.stderr}")
            
    except FileNotFoundError:
        print(f"Script not found: {script_path}")

def is_ipv6(address):
  """
  Checks if a string is a valid IPv6 address.

  Args:
    address: The string to check.

  Returns:
    True if the address is a valid IPv6 address, False otherwise.
  """
  try:
    ipaddress.IPv6Address(address)
    return True
  except ipaddress.AddressValueError:
    return False

def find_IpAddr(json_string, search):
    """
    Finds and extracts all 'cpeIpv6Addr' values from a JSON string.

    Args:
      json_string: The JSON string to search.

    Returns:
      A list of 'cpeIpv6Addr' values found in the JSON string.
    """
    try:
        data = json.loads(json_string)
        match = "" 

        for result_item in data['data']['result']:
            match = result_item['metric'][search]
            return match

    except json.JSONDecodeError:
        print("Invalid JSON string.")
        return
    except KeyError:
        #print(f"Can't find {search}")
        return

def is_ipv6(address):
  """
  Checks if a string is a valid IPv6 address.

  Args:
    address: The string to check.

  Returns:
    True if the address is a valid IPv6 address, False otherwise.
  """
  try:
    ipaddress.IPv6Address(address)
    return True
  except ipaddress.AddressValueError:
    return False
    
def is_ipv4(address):
  """
  Checks if a string is a valid IPv4 address.

  Args:
    address: The string to check.

  Returns:
    True if the address is a valid IPv4 address, False otherwise.
  """
  try:
    ipaddress.IPv4Address(address)
    return True
  except ipaddress.AddressValueError:
    return False
path = "./toybox-main"
# path = "C:/Users/mmorri890/Documents/AmpPython/James EC_FDX_AMP Python Scripts/toybox-main"
#path = "C:/Users/mmorri890/Documents/AmpPython/James EC_FDX_AMP Python Scripts/CM & RPD Data Collector (v2.1.3 and v2.2.3w)"
if len(sys.argv)== 4:  # Check if exactly 3 arguments are provided
    Short_output = True
    # Assign arguments to variables
    arg1 = sys.argv[1]   # 'PROD or 'DEV', CM in Prod or Dev (preprod) environment
    arg2 = sys.argv[2]  # 'CM' or 'CPE', need CM IP or CPE IP
    arg3 = sys.argv[3]  # list of CM MAC addresses
else:
    Short_output = False
    # for manual and multiple mac vs ip lookup
    print("Please provide 3 arguments: PROD or DEV, CM or CPE, MACs")
    arg1 = 'PROD'   # 'PROD or 'DEV', CM in Prod or Dev (preprod) environment
    arg2 = 'CPE'  # 'CM' or 'CPE', need CM IP or CPE IP
    #arg3 = ["24:a1:86:00:45:60","24:a1:86:00:c5:8c","24:a1:86:00:c5:98","24:a1:86:00:40:e4","24:a1:86:00:c1:40","24:a1:86:00:45:8c","24:a1:86:00:c5:84","24:a1:86:00:41:30","24:a1:86:00:c5:7c","24:a1:86:00:45:64","24:a1:86:00:41:34","24:a1:86:00:41:44","24:a1:86:00:45:68"]  # list of CM MAC addresses
    arg3 = ['8c:76:3f:f0:78:b0','8c:76:3f:f0:78:c4','10:e1:77:58:d1:78','ac:db:48:bb:d0:c0','ac:db:48:bb:cf:c8','ac:db:48:bb:cf:ec','10:e1:77:58:d1:ac','ac:db:48:bb:cf:e8','8c:76:3f:f0:79:b0','ac:db:48:bb:cf:14','ac:db:48:bb:cf:10','10:e1:77:58:d1:88','ac:db:48:bb:cf:e0','ac:db:48:bb:cf:0c']  # list of CM MAC addresses
    arg3 = ['aa:76:3f:f0:78:b0','8c:76:3f:f0:78:c4','10:e1:77:58:d1:78','ac:db:48:bb:d0:c0','ac:db:48:bb:cf:c8','ac:db:48:bb:cf:ec','10:e1:77:58:d1:ac','ac:db:48:bb:cf:e8','8c:76:3f:f0:79:b0','ac:db:48:bb:cf:14','ac:db:48:bb:cf:10','10:e1:77:58:d1:88','ac:db:48:bb:cf:e0','ac:db:48:bb:cf:0c']  # list of CM MAC addresses


if arg1 == "PROD":
    url = "https://sat-prod.codebig2.net/v2/ws/token.oauth2"
    PROD_secret = os.environ.get("PROD_API_KEY")
    if PROD_secret is None:
        print("PROD_API_KEY environment variable not set.")
        sys.exit(1)
    secret = PROD_secret
    tag = 'prod'
elif arg1 == "DEV":
    url = "https://sat-stg.codebig2.net/v2/ws/token.oauth2"
    DEV_secret = os.environ.get("DEV_API_KEY")
    if DEV_secret is None:
        print("DEV_API_KEY environment variable not set.")
        sys.exit(1)
    secret = DEV_secret
    tag = 'dev'
if arg2 == "CM":
    k_matrix = 'K_CmRegStatus_Config'
    find_ipv4 = 'ipV4Addr'
    find_ipv6 = 'ipv6Addr'
elif arg2 == "CPE":
    k_matrix = 'K_CmCpeList'
    find_ipv4 = 'cpeIpv4Addr'
    find_ipv6 = 'cpeIpv6Addr'
        
script = os.path.join(path, 'websec.py')
arguments = ["thanos-prod", "--url", url, "--id", "ngan-hs", "--secret", secret, "--scope", "ngan:telemetry:thanosapi"]
run_script(script, arguments)
arguments = [f"thanos-{tag}", "--bearer"]
token = run_script_and_get_result(script, arguments)
#print(f"Token updated: {token}")

# if arg3 is a string, convert it to a list
if isinstance(arg3, str):
    mac_list = [arg3]
else:
    mac_list = arg3
# re-iterate the loop for multiple mac
for mac in mac_list:
    arguments = [f"--{tag}", k_matrix, f"cmMacAddr={mac}"]
    script = os.path.join(path, "thanos2.py")
    result = run_script_and_get_result(script, arguments)
    #print(result)
    # Get the IP address
    ip = find_IpAddr(result, find_ipv4)   #ipV4Addr, ipv6Addr, cpeIpv6Addr
    if is_ipv4(ip) and not ip == '0.0.0.0':
        if Short_output:
            print(ip)
        else:
            print(f"CM MAC = {mac}, {find_ipv4} = {ip}")
    else:
        ip = find_IpAddr(result, find_ipv6)
        if is_ipv6(ip):
            if Short_output:
                print(ip)
            else:
                print(f"CM MAC = {mac}, {find_ipv6} = {ip}")
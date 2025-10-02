import numpy as np
import pandas as pd
import sys
import argparse
# import subprocess
import paramiko, os
from paramiko.proxy import ProxyCommand
from contextlib import contextmanager

@contextmanager
def ssh_connect(host_alias):
    cfg = paramiko.SSHConfig()
    with open(os.path.expanduser("~/.ssh/config")) as f:
        cfg.parse(f)
    host_cfg = cfg.lookup(host_alias)

    proxy = ProxyCommand(host_cfg['proxycommand']) if 'proxycommand' in host_cfg else None

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host_cfg['hostname'],
        username=host_cfg.get('user'),
        key_filename=os.path.expanduser(host_cfg.get('identityfile', [None])[0]),
        sock=proxy
    )
    try:
        yield client
    finally:
        client.close()

parser = argparse.ArgumentParser()
parser.add_argument("csv_file_path")
parser.add_argument("machine", nargs="?", default="local")
parser.add_argument("-v", "--verbose", action="store_true")
args = parser.parse_args()
csv_file_path = args.csv_file_path
machine = args.machine
verbose = args.verbose

print(f"CSV relative path: {csv_file_path}")
print(f"Server: {machine}")
# Read the CSV without treating the blank line as NaN
df = pd.read_csv(csv_file_path, keep_default_na=False)

# Find the index of the first completely blank row (all empty strings)
blank_row_index = df.index[df.apply(lambda row: all(cell == '' for cell in row), axis=1)].tolist()
if blank_row_index:
    split_idx = blank_row_index[0]
else:
    print("\nDidn't find blank row!\n".capitalize())
    sys.exit(1)
# === Top section: one dict per row ===
top_df = df.iloc[:split_idx]
versions = top_df.to_dict(orient='records')
# === Bottom section: combine into one dict ===
bottom_df = df.iloc[split_idx + 1:]  # skip blank line
# Only keep rows where the first column (key) is not empty
bottom_df = bottom_df[bottom_df.iloc[:, 0] != '']
bench_info = dict(zip(bottom_df.iloc[:, 0], bottom_df.iloc[:, 1]))

# Extract doubles
time_per_tet = float(bench_info['approx time per tet (s)'])
max_ram_per_tet = float(bench_info['approx max ram per tet (KB)'])
# Evaluate the numpy expression string safely
# Define an "eval" environment with numpy available
safe_env = {"np": np}
numtets = eval(bench_info['total numtets'], safe_env)

if verbose:
    # === Example outputs ===
    print("=== Versions ===")
    df_versions = pd.DataFrame(versions)
    # Let pandas handle the pretty printing
    # You can tweak display width and column wrapping
    with pd.option_context('display.max_rows', None,
                        'display.max_columns', None,
                        'display.max_colwidth', 100,   # wrap long text
                        'display.width', 120):
        print(df_versions)
    print("\n=== Benchmark Info ===")
    max_key_len = max(len(k) for k in bench_info.keys())
    for k, v in bench_info.items():
        v_str = str(v)
        if len(v_str) > 80:  # wrap long text manually
            wrapped = [v_str[i:i+80] for i in range(0, len(v_str), 80)]
            # first line stays left-aligned, continuation lines right-aligned
            print(f"{k.ljust(max_key_len)} : {wrapped[0]}")
            for cont in wrapped[1:]:
                print(" " * (max_key_len + 3) + cont.rjust(len(cont)))
        else:
            print(f"{k.ljust(max_key_len)} : {v_str}")
    print("\ntime_per_tet:", time_per_tet, type(time_per_tet))
    print("max_ram_per_tet:", max_ram_per_tet, type(max_ram_per_tet))
    print("numtets:", numtets, type(numtets))

if machine != "local":
    with ssh_connect(machine+"python") as ssh:
        stdin, stdout, stderr = ssh.exec_command("top -b -n 1 | head -n 15")
        print(f"\n=========================== top processes on {machine} ===========================")
        print(stdout.read().decode(), end="")
        print("===============================================================================\n")

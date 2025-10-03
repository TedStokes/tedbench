import numpy as np
import pandas as pd
import sys
import argparse
import subprocess
import paramiko, os
from paramiko.proxy import ProxyCommand
from contextlib import contextmanager

def line(statement):
    n = 78-len(statement)
    return "="*(n//2) +" "+ statement +" "*(1+n%2)+ "="*(n//2)

def human_format(num, sig=2):
    return f"{num:.{sig}g}"

@contextmanager
def ssh_connect(host_alias):
    if host_alias=="local":
        try:
            yield None
        finally:
            pass
    else:
        cfg = paramiko.SSHConfig()
        with open(os.path.expanduser("~/.ssh/config")) as f:
            cfg.parse(f)
        host_cfg = cfg.lookup(host_alias+"python")

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
            print(line("CLOSING SSH CONNECTION"))
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
numtets = eval(bench_info['numtets'], safe_env)

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

with ssh_connect(machine) as ssh:
    command = "top -b -n 1 | head -n 15"
    print("\n"+line(f"top processes on {machine}"))
    if machine == "local":
        print(subprocess.run(command, shell=True, capture_output=True, text=True).stdout, end="")
    else:
        stdin, stdout, stderr = ssh.exec_command(command)
        print(stdout.read().decode(), end="")
    print("="*80+"\n")

    print(f"Numbers of tets:   ", end="")
    for n in numtets[:-1]:
        print(human_format(n), end=", ")
    print(human_format(numtets[-1]))
    mesh_sizes = [max(2, round(s)) for s in np.cbrt(numtets/6)]
    if verbose:
        print(f"{mesh_sizes=}")
    print(f"Total number of tets:   {human_format(sum(numtets), 3)}")
    print(f"Approx maximum RAM usage (GB):   {human_format(max_ram_per_tet*max(numtets)/1e6)}")
    print(f"Approx total CPU time (seconds, excludes prep):   {human_format(time_per_tet*sum(numtets))}")

    # if input("\nConfirm benchmark should run? yes/no:   ").lower() not in ["yes", "y"]:
    #     print(line("CANCELLING BENCHMARK"))
    #     quit()

    print("\n"+line("WRITING BASH SCRIPT"))
    bash_script = """#!/bin/bash
: > stdout.log
: > stderr.log
: > time.log
for s in"""

    for s in mesh_sizes:
        bash_script += f" {s}"
    bash_script += """
do"""

    for command in bench_info['prep command'].split(" && "):
        bash_script += f"""
    {command}"""
        
    bash_script += '''
    let num=$s*$s*$s*6
    echo $s "*" $s "*" $s "* 6 = " $num " tets"'''

    for version in versions:
        run_command = bench_info['default run command']
        if version['custom run command'] != "":
            run_command = version['custom run command']
        bash_script += f'''
    echo "{version["version label"]}"
    /bin/time -v -o tmp_time.log \\
      ~/{version["build location"]}/dist/bin/{run_command} \\
      > >(tee -a "stdout.log") \\
      2> >(tee -a "stderr.log" >&2) \\
      | grep {bench_info["grep args"]}
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log
    {bench_info["per run cleanup command"]}
    echo ""'''
        
    bash_script += f'''
    {bench_info["final cleanup command"]}
    rm tmp_time.log
done'''
    
    print(bash_script)

import numpy as np
import pandas as pd
import sys
import argparse
import subprocess
import paramiko, os
from paramiko.proxy import ProxyCommand
from contextlib import contextmanager
from datetime import datetime
import matplotlib.pyplot as plt
import re

def line(statement):
    n = 78-len(statement)
    return "="*(n//2) +" "+ statement +" "*(1+n%2)+ "="*(n//2)

def human_format(num, sig=2):
    return f"{num:.{sig}g}"

def extract_number(line):
    nums = re.findall(r'\d+\.?\d*', line)
    if len(nums) == 0:
        return np.NaN
    elif len(nums) > 1:
        ValueError("Multiple values detected on 1 line")
    return float(nums[0]) if '.' in nums[0] else int(nums[0])

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
parser.add_argument(
    "csv_files",
    nargs='+',
    help="CSV file paths optionally followed by some ':<run_name>'s"
)
parser.add_argument("-v", "--verbose", action="store_true")
parser.add_argument("-l", "--log", action="store_true")
parser.add_argument("-s", '--suffix', type=str, default="")
args = parser.parse_args()
verbose = args.verbose

# Process each csv_file argument
csv_files_info = []
for entry in args.csv_files:
    if ':' in entry:
        split = entry.split(':')
        path = split[0]
        runs = split[1:]
        print(type(split))
    else:
        path, runs = entry, ['ALL']
    csv_files_info.append({"path": path, "runs": runs})
for info in csv_files_info:
    print(f"File: {info['path']}, Runs: {info['runs']}")

all_phrases = set()
all_values = {}
print(line("GETTING DATA"))
for csv_file_info in csv_files_info:
    csv_file_path = csv_file_info['path']
    print(f"CSV path: {csv_file_path}")
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
    machine = bench_info['machine']
    print(f"Machine: {machine}")
    if csv_file_info['runs'][0] == 'ALL':
        runs = [version['version label'] for version in versions]
    else:
        runs = csv_file_info['runs']
    print(f"Runs: ", end="")
    for run in runs[:-1]:
        print(run, end=", ")
    print(f"{runs[-1]}")

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

    # Write graphing time to history
    with open("history.txt", "a") as file:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{now} - graphing {csv_file_path[:-4]}\n")

    # Delete tmux session and download data file if remote
    tmux_name = f'tedbench_{csv_file_path[:-4].replace("/","_")}'
    if machine != "local":
        with ssh_connect(machine) as ssh:
            stdin, stdout, stderr = ssh.exec_command(f'tmux kill-session -t {tmux_name} 2>/dev/null')
            with ssh.open_sftp() as sftp:
                sftp.get(f'tedbench/{csv_file_path[:-4]}/data.txt', f'{csv_file_path[:-4]}/data.txt')
    else:
        subprocess.run(f'tmux kill-session -t {tmux_name} 2>/dev/null', shell=True, capture_output=True, text=True)

    with open(f"{csv_file_path[:-4]}/data.txt", "r") as f:
        string_data = f.read()

    numtets_str = re.findall(r'\* 6 =\s+(\d+)\s+tets', string_data)
    numtets = [int(num) for num in numtets_str]
    if verbose:
        print(f"{numtets=}")
    phrases = bench_info['grep args'].split(' -e')[1:]
    phrases = [phrase[2:-1] for phrase in phrases]
    phrases.append("Maximum resident set size (kbytes): ")
    all_phrases.update(phrases)
    if verbose:
        print(f"{phrases=}")
    for version in runs:
        values = {phrase: [] for phrase in phrases}
        values['numtets'] = numtets
        if verbose:
            print(f"{version=}")
        blocks = string_data.split("\n\n")
        for block in blocks:
            lines = block.splitlines()
            if version in lines:
                if verbose:
                    print(lines[-len(phrases):])
                for phrase in phrases:
                    for line in lines:
                        if phrase in line:
                            values[phrase].append(extract_number(line))
        for phrase in phrases:
            if len(values[phrase]) != len(numtets):
                ValueError("Missing values")
        run_key = f"{version} ({csv_file_path[:-4]})" if len(csv_files_info) > 1 else version
        all_values[run_key] = values

translate = {
    'InputXml CPU Time: ': ['InputXml time', 's', 1],
    'OutputVtk CPU Time: ': ['OutputVtu time', 's', 1],
    'Maximum resident set size (kbytes): ': ['Peak ram usage', 'GB', 1e6],
}
custom_labels = []
suffix = args.suffix
log = args.log

for phrase in all_phrases:
    format = translate[phrase]
    plt.figure(figsize=(7,5))
    title = f"{format[0]}" if len(csv_files_info) > 1 else f"{format[0]} - {bench_info['benchmark title']}"
    plt.title(title)
    plt.xlabel("Number of tets", fontsize=12)
    plt.ylabel(f"{format[0]} ({format[1]})", fontsize=12)
    i=0
    for run_key, values in all_values.items():
        if phrase in values:
            label = run_key if len(custom_labels)==0 else custom_labels[i]
            i += 1
            x = np.array(values['numtets'])
            y = np.array(values[phrase])
            plt.plot(x, y/format[2], marker='o', linestyle='-', label=label)
    if log:
        plt.xscale('log')
        plt.yscale('log')
    plt.xticks(fontsize=12)
    plt.yticks(fontsize=12)
    plt.legend(fontsize=12)
    plt.grid(True)
    plt.tight_layout()
    png_path = f"{csv_files_info[0]['path'][:-4]}/{format[0].replace(' ', '_').lower()}{suffix}"
    png_path += "_log.png" if log else ".png"
    plt.savefig(png_path, dpi=300)



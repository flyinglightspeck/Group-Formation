import heapq
import itertools
import os
import json
import csv
import subprocess
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import xlsxwriter as xlsxwriter

from config import Config
import pandas as pd
import glob
import re
import matplotlib as mpl
from matplotlib import rcParams
from matplotlib import ticker


def write_json(fid, results, directory, is_clique):
    file_name = f"{fid:05}.c.json" if is_clique else f"{fid:05}.json"
    with open(os.path.join(directory, 'json', file_name), "w") as f:
        json.dump(results, f)


def create_csv_from_json(directory, duration=0):
    if not os.path.exists(directory):
        return

    headers_set = set()
    rows = []
    node_rows = []

    json_dir = os.path.join(directory, 'json')
    filenames = os.listdir(json_dir)
    filenames.sort()

    # for filename in filenames:
    #     if filename.endswith('.c.json'):
    print(directory)
    if len(filenames) == 0:
        return
    with open(os.path.join(json_dir, filenames[0])) as f:
        try:
            data = json.load(f)
            headers_set = headers_set.union(set(list(data.keys())))
        except json.decoder.JSONDecodeError:
            print(filenames[0])

    headers = list(headers_set)
    headers.sort()
    rows.append(['fid'] + headers)
    node_rows.append(['fid'] + headers)

    # weights = []
    min_dists = []
    avg_dists = []
    max_dists = []
    for filename in filenames:
        if filename.endswith('.json'):
            with open(os.path.join(json_dir, filename)) as f:
                try:
                    data = json.load(f)
                    fid = filename.split('.')[0]
                    row = [fid] + [data[h] if h in data else 0 for h in headers]
                    node_rows.append(row)
                    if filename.endswith('.c.json'):
                        rows.append(row)
                        # weights.append(data['5 weight'])
                        # min_dists.append(data['1 min dist'])
                        # avg_dists.append(data['2 avg dist'])
                        # max_dists.append(data['3 max dist'])
                except json.decoder.JSONDecodeError:
                    print(filename)

    with open(os.path.join(directory, 'cliques.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)

    with open(os.path.join(directory, 'nodes.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(node_rows)


def write_csv(directory, rows, name):
    with open(os.path.join(directory, 'metrics.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def write_hds_time(hds, directory, nid):
    if not os.path.exists(directory):
        return

    headers = ['timestamp(s)', 'relative_time(s)', 'hd']
    rows = [headers]

    for i in range(len(hds)):
        row = [hds[i][0], hds[i][0] - hds[0][0], hds[i][1]]
        rows.append(row)

    with open(os.path.join(directory, f'hd-n{nid}.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def write_hds_round(hds, rounds, directory, nid):
    if not os.path.exists(directory):
        return

    headers = ['round', 'time(s)', 'hd']
    rows = [headers]

    for i in range(len(hds)):
        row = [i+1, rounds[i+1] - rounds[0], hds[i][1]]
        rows.append(row)

    with open(os.path.join(directory, f'hd-n{nid}.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def write_swarms(swarms, rounds, directory, nid):
    headers = [
        'timestamp(s)',
        'relative times(s)',
        'num_swarms',
        'average_swarm_size',
        'largest_swarm',
        'smallest_swarm',
    ]

    rows = [headers]

    for i in range(len(swarms)):
        t = swarms[i][0] - rounds[0]
        num_swarms = len(swarms[i][1])
        sizes = swarms[i][1].values()

        row = [swarms[i][0], t, num_swarms, sum(sizes)/num_swarms, max(sizes), min(sizes)]
        rows.append(row)

    with open(os.path.join(directory, f'swarms-n{nid}.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def write_configs(directory, date_time):
    headers = ['config', 'value']
    rows = [headers]
    kargs = vars(Config).items()

    for k, v in kargs:
        if not k.startswith('__'):
            rows.append([k, v])
    rows.append(["datetime", date_time])

    with open(os.path.join(directory, 'config.csv'), 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)


def combine_csvs(directory, xslx_dir, file_name):
    csv_files = glob.glob(os.path.join(directory, "*.csv"))

    with pd.ExcelWriter(os.path.join(xslx_dir, f'{file_name}.xlsx')) as writer:
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            sheet_name = os.path.split(csv_file)[-1][:-4]
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def combine_csvs_with_formula(directory, xslx_dir, file_name):
    csv_files = glob.glob(os.path.join(directory, "*.csv"))

    with pd.ExcelWriter(os.path.join(xslx_dir, f'{file_name}.xlsx'), engine='xlsxwriter',
                        engine_kwargs={'options': {'strings_to_numbers': True}}) as writer:
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            sheet_name = os.path.split(csv_file)[-1][:-4]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            if sheet_name == 'metrics':
                worksheet = writer.sheets['metrics']
                worksheet.write('A16', 'min radio range')
                worksheet.write_formula(f'B16', f'=MIN(nodes!H:H)')


def combine_xlsx(directory, rs):
    rdfs = dict()
    for r in rs:
        rdfs[str(r)] = []

    xlsx_files = glob.glob(os.path.join(directory, "*.xlsx"))
    for file in sorted(xlsx_files):
        print(file)
        df = pd.read_excel(file, sheet_name='metrics')
        m = re.search(r'G(\d+)_R(\d+)', file)
        k = m.group(1)
        r = m.group(2)

        df2 = pd.DataFrame([k, r])
        df3 = pd.concat([df2, df.value])
        rdfs[r].append(df3)

    data_frames = []
    for dfs_r in rdfs.values():
        if len(dfs_r):
            data_frames.append(pd.concat([pd.concat([pd.DataFrame(['G', 'R']), df.metric])] + dfs_r[:20], axis=1))

    return pd.concat(data_frames)


def combine_xlsx_with_formula(directory, rs, shape=False):
    rdfs = dict()
    for r in rs:
        rdfs[str(r)] = []

    metric_titles = [
        'min radio range',
        'avg radio range',
        'max radio range',
        'min requested expansion',
        'avg requested expansion',
        'max requested expansion',
        'min neighbor driven expansion',
        'avg neighbor driven expansion',
        'max neighbor driven expansion',
        'num lazy nodes',
        'total sent bytes',
        'total received bytes',
        'min num heuristic ran',
        'avg num heuristic ran',
        'max num heuristic ran',
    ]

    xlsx_files = glob.glob(os.path.join(directory, "*.xlsx"))
    for file in sorted(xlsx_files):
        print(file)
        try:
            df = pd.read_excel(file, sheet_name=['metrics', 'nodes'])
        except ValueError as e:
            print(e)
            continue
        nodes_df = df['nodes']
        min_radio_range = nodes_df['3 max range'].loc[nodes_df['3 max range'].idxmin()]
        avg_radio_range = nodes_df['3 max range'].mean()
        max_radio_range = nodes_df['3 max range'].loc[nodes_df['3 max range'].idxmax()]
        min_requested_expansion = nodes_df['3 number of requested expansions'].loc[nodes_df['3 number of requested expansions'].idxmin()]
        avg_requested_expansion = nodes_df['3 number of requested expansions'].mean()
        max_requested_expansion = nodes_df['3 number of requested expansions'].loc[nodes_df['3 number of requested expansions'].idxmax()]
        min_nd_expansion = nodes_df['3 number of neighbor driven expansions'].loc[nodes_df['3 number of neighbor driven expansions'].idxmin()]
        avg_nd_expansion = nodes_df['3 number of neighbor driven expansions'].mean()
        max_nd_expansion = nodes_df['3 number of neighbor driven expansions'].loc[nodes_df['3 number of neighbor driven expansions'].idxmax()]
        num_lazy_nodes = (nodes_df['3 solution range'] == 0).sum()
        total_sent_bytes = nodes_df['B_bytes_sent'].sum()
        total_received_bytes = nodes_df['B_bytes_received'].sum()
        min_num_h_ran = nodes_df['4 h invoked'].loc[nodes_df['4 h invoked'].idxmin()]
        avg_num_h_ran = nodes_df['4 h invoked'].mean()
        max_num_h_ran = nodes_df['4 h invoked'].loc[nodes_df['4 h invoked'].idxmax()]

        node_metrics = pd.DataFrame([
            min_radio_range,
            avg_radio_range,
            max_radio_range,
            min_requested_expansion,
            avg_requested_expansion,
            max_requested_expansion,
            min_nd_expansion,
            avg_nd_expansion,
            max_nd_expansion,
            num_lazy_nodes,
            total_sent_bytes,
            total_received_bytes,
            min_num_h_ran,
            avg_num_h_ran,
            max_num_h_ran,
        ])

        df = df['metrics']
        if shape:
            m = re.search(r'(\w+)_G(\d+)', file)
            r = m.group(1)
            k = m.group(2)
        else:
            m = re.search(r'G(\d+)_R(\d+)', file)
            k = m.group(1)
            r = m.group(2)

        df2 = pd.DataFrame([k, r])
        df3 = pd.concat([df2, df.value, node_metrics])
        if r in rdfs:
            rdfs[r].append(df3)

    data_frames = []
    for dfs_r in rdfs.values():
        if len(dfs_r):
            data_frames.append(
                pd.concat(
                    [
                        pd.concat([pd.DataFrame(['G', 'R']),
                                   df.metric,
                                   pd.DataFrame(metric_titles)])] + dfs_r[:10],
                    axis=1)
            )

    return pd.concat(data_frames)


def combine_xlsx_with_formula_static(directory, rs):
    rdfs = dict()
    for r in rs:
        rdfs[str(r)] = []

    metric_titles = [
        'min radio range',
        'avg radio range',
        'max radio range',
        'min solution radio range',
        'avg solution radio range',
        'max solution radio range',
        'num lazy nodes',
        'total sent bytes',
        'total received bytes',
        'min num heuristic ran',
        'avg num heuristic ran',
        'max num heuristic ran',
    ]

    xlsx_files = glob.glob(os.path.join(directory, "*.xlsx"))
    for file in sorted(xlsx_files):
        print(file)
        df = pd.read_excel(file, sheet_name=['metrics', 'nodes'])
        nodes_df = df['nodes']
        min_radio_range = nodes_df['3 max range'].loc[nodes_df['3 max range'].idxmin()]
        avg_radio_range = nodes_df['3 max range'].mean()
        max_radio_range = nodes_df['3 max range'].loc[nodes_df['3 max range'].idxmax()]
        min_solution_radio_range = nodes_df['3 solution range'].loc[nodes_df['3 solution range'].idxmin()]
        avg_solution_radio_range = nodes_df['3 solution range'].mean()
        max_solution_radio_range = nodes_df['3 solution range'].loc[nodes_df['3 solution range'].idxmax()]
        num_lazy_nodes = (nodes_df['3 solution range'] == 0).sum()
        total_sent_bytes = nodes_df['B_bytes_sent'].sum()
        total_received_bytes = nodes_df['B_bytes_received'].sum()
        min_num_h_ran = nodes_df['4 h invoked'].loc[nodes_df['4 h invoked'].idxmin()]
        avg_num_h_ran = nodes_df['4 h invoked'].mean()
        max_num_h_ran = nodes_df['4 h invoked'].loc[nodes_df['4 h invoked'].idxmax()]

        node_metrics = pd.DataFrame([
            min_radio_range,
            avg_radio_range,
            max_radio_range,
            min_solution_radio_range,
            avg_solution_radio_range,
            max_solution_radio_range,
            num_lazy_nodes,
            total_sent_bytes,
            total_received_bytes,
            min_num_h_ran,
            avg_num_h_ran,
            max_num_h_ran,
        ])

        df = df['metrics']
        m = re.search(r'G(\d+)_R(\d+)', file)
        k = m.group(1)
        r = m.group(2)
        df2 = pd.DataFrame([k, r])
        df3 = pd.concat([df2, df.value, node_metrics])
        rdfs[r].append(df3)

    data_frames = []
    for dfs_r in rdfs.values():
        if len(dfs_r):
            data_frames.append(
                pd.concat(
                    [
                        pd.concat([pd.DataFrame(['G', 'R']),
                                   df.metric,
                                   pd.DataFrame(metric_titles)])] + dfs_r[:10],
                    axis=1)
            )

    return pd.concat(data_frames)


def combine_groups(directory, name, df_list, sheet_names, rs, num_exp):

    with pd.ExcelWriter(os.path.join(directory, f'{name}.xlsx'), engine='xlsxwriter',
                        engine_kwargs={'options': {'strings_to_numbers': True}}) as writer:

        for df, g in zip(df_list, sheet_names):
            sheet_name = f'G{g}'
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            worksheet = writer.sheets[sheet_name]
            workbook = writer.book
            cell_format_bold = workbook.add_format()
            cell_format_bold.set_bold()

            if num_exp == 10:
                cols = ['K', 'L', 'M', 'N', 'O', 'P', 'Q']
            elif num_exp == 3:
                cols = ['D', 'E', 'F', 'G', 'H']
            else:
                cols = ['U', 'V', 'W', 'X', 'Y']

            worksheet.write(f'{cols[1]}1', 'Min', cell_format_bold)
            worksheet.write(f'{cols[2]}1', 'Avg', cell_format_bold)
            worksheet.write(f'{cols[3]}1', 'Max', cell_format_bold)
            worksheet.write(f'{cols[4]}1', 'Median', cell_format_bold)

            for row in range(4, len(df)+2):
                if row % 31 == 16 or row % 31 == 17:
                    continue

                cell_format_bordered_avg = workbook.add_format()
                cell_format_bordered_all = workbook.add_format()
                cell_format_bordered_avg.set_bottom(row % 31 == 1)
                cell_format_bordered_all.set_bottom(row % 31 == 1)
                cell_format_bordered_avg.set_bold(any([row % 31 == r for r in [0, 4, 9, 14, 15]]))
                if row % 31 == 28 or row % 31 == 29:
                    worksheet.write_formula(f'{cols[1]}{row}', f'=MIN(B{row}:{cols[0]}{row})/(1024*1024)',
                                            cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[2]}{row}',
                                            f'=(SUM(B{row}:{cols[0]}{row})-MIN(B{row}:{cols[0]}{row})-MAX(B{row}:{cols[0]}{row}))/{num_exp - 2}/(1024*1024)',
                                            cell_format_bordered_avg)
                    worksheet.write_formula(f'{cols[3]}{row}', f'=MAX(B{row}:{cols[0]}{row})/(1024*1024)',
                                            cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[4]}{row}', f'=MEDIAN(B{row}:{cols[0]}{row})/(1024*1024)',
                                            cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[5]}{row}', f'=8*{cols[2]}{row}/{cols[2]}{4+(row//31)*31}',
                                            cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[6]}{row}', f'={cols[5]}{row}/1024',
                                            cell_format_bordered_all)
                else:
                    worksheet.write_formula(f'{cols[1]}{row}', f'=MIN(B{row}:{cols[0]}{row})', cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[2]}{row}',
                                            f'=(SUM(B{row}:{cols[0]}{row})-MIN(B{row}:{cols[0]}{row})-MAX(B{row}:{cols[0]}{row}))/{num_exp - 2}',
                                            cell_format_bordered_avg)
                    worksheet.write_formula(f'{cols[3]}{row}', f'=MAX(B{row}:{cols[0]}{row})', cell_format_bordered_all)
                    worksheet.write_formula(f'{cols[4]}{row}', f'=MEDIAN(B{row}:{cols[0]}{row})', cell_format_bordered_all)




def read_cliques_xlsx(path):
    df = pd.read_excel(path, sheet_name='nodes')
    return [np.array(eval(c)) for c in df["7 coordinates"]]


def elastic_post_process(path):
    xlsx_files = glob.glob(os.path.join(path, "*.xlsx"))

    for f in xlsx_files:
        m = re.search(r'(\d+_(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)_\d+_\d+_\d+)', f)
        # m = re.search(r'_(\d+).xlsx$', f)
        datetime = m.group(1)
        exp_path = os.path.join(path, datetime)
        create_csv_from_json(exp_path)

    time.sleep(1)

    for f in xlsx_files:
        m = re.search(r'(\d+_(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)_\d+_\d+_\d+)', f)
        # m = re.search(r'_(\d+).xlsx$', f)
        datetime = m.group(1)
        print(datetime)
        exp_path = os.path.join(path, datetime)
        out_path = os.path.join(path, "processed")
        combine_csvs(exp_path, out_path, os.path.split(f)[-1][:-5])


def merge_network_heuristic_timelines(path, fid='*'):
    network_files = glob.glob(os.path.join(path, f"nt_{fid}.n.json"))
    heuristic_files = glob.glob(os.path.join(path, f"ht_{fid}.h.json"))
    network_timelines = []
    heuristic_timelines = []

    for f in network_files:
        with open(f) as jf:
            network_timelines.append(json.load(jf))

    for f in heuristic_files:
        with open(f) as jf:
            heuristic_timelines.append(json.load(jf))

    start_time = min([tl[0][0] for tl in network_timelines + heuristic_timelines if len(tl)])

    if len(network_timelines) > 1:
        network_timelines = merge_timelines(network_timelines)
        heuristic_timelines = merge_timelines(heuristic_timelines)
    else:
        network_timelines = network_timelines[0]
        heuristic_timelines = heuristic_timelines[0]

    return {
        "start_time": start_time,
        "sent_bytes": list(filter(lambda x: x[1] == 's', network_timelines)),
        "received_bytes": list(filter(lambda x: x[1] == 'r', network_timelines)),
        "heuristic": heuristic_timelines
    }


def gen_sliding_window_chart_data(timeline, start_time, value_fn, sw=0.0005):  # 500 micro second
    xs = [0]
    ys = [0]

    while len(timeline):
        event = timeline[0]
        t = event[0] - start_time
        if xs[-1] <= t < xs[-1] + sw:
            ys[-1] += value_fn(event)
            timeline.pop(0)
        else:
            xs.append(xs[-1] + sw)
            ys.append(0)

    return xs, ys


def merge_timelines(timelines):
    lists = timelines
    heap = []
    for i, lst in enumerate(lists):
        if lst:
            heap.append((lst[0][0], i, 0))
    heapq.heapify(heap)

    merged = []
    while heap:
        val, lst_idx, elem_idx = heapq.heappop(heap)
        merged.append(lists[lst_idx][elem_idx] + [lst_idx])
        if elem_idx + 1 < len(lists[lst_idx]):
            next_elem = lists[lst_idx][elem_idx + 1][0]
            heapq.heappush(heap, (next_elem, lst_idx, elem_idx + 1))
    return merged


def gen_sw_charts(path_1, path_2, fid):
    fig, [ax0, ax1] = plt.subplots(2, 1, figsize=(5.25, 3.5))
    data_1 = merge_network_heuristic_timelines(path_1, fid)
    data_2 = merge_network_heuristic_timelines(path_2, fid)

    r_xs_1, r_ys_1 = gen_sliding_window_chart_data(data_1['received_bytes'], data_1['start_time'], lambda x: x[2])
    s_xs_1, s_ys_1 = gen_sliding_window_chart_data(data_1['sent_bytes'], data_1['start_time'], lambda x: x[2])
    r_xs_2, r_ys_2 = gen_sliding_window_chart_data(data_2['received_bytes'], data_2['start_time'], lambda x: x[2])
    s_xs_2, s_ys_2 = gen_sliding_window_chart_data(data_2['sent_bytes'], data_2['start_time'], lambda x: x[2])
    # h_xs, h_ys = gen_sliding_window_chart_data(data['heuristic'], data['start_time'], lambda x: 1)
    ax0.step(s_xs_2, s_ys_2, where='post', label="RS", color="#ffa600")
    ax0.step(s_xs_1, s_ys_1, where='post', label="CANF", color="#004a6c")
    ax1.step(r_xs_2, r_ys_2, where='post', label="RS", color="#ffa600")
    ax1.step(r_xs_1, r_ys_1, where='post', label="CANF", color="#004a6c")
    # ax.step(h_xs, h_ys, where='post', label="Heuristic invoked")
    ax0.legend(loc='upper right')
    ax0.set_ylabel('Transmitted Data (Byte)', loc='top', rotation=0, labelpad=-95)
    ax0.set_xlabel('Time (Millisecond)', loc='right')
    ax0.set_xlim([7.45, 7.55])
    ax0.set_ylim([0, 700])
    ax0.xaxis.set_major_formatter(lambda x, pos: str(int(x*1000)))
    ax0.xaxis.set_major_locator(ticker.MultipleLocator(0.01))
    ax0.yaxis.set_major_locator(ticker.MultipleLocator(200))
    ax0.margins(y=0)
    # ax0.set_ylim([0, 600])
    ax0.spines['top'].set_color('white')
    ax0.spines['right'].set_color('white')
    # ax0.set_yscale('log')

    ax1.legend(loc='upper right')
    ax1.set_ylabel('Received Data (Byte)', loc='top', rotation=0, labelpad=-85)
    ax1.set_xlabel('Time (Millisecond)', loc='right')
    ax1.set_xlim([7.45, 7.55])
    ax1.set_ylim([0, 9000])
    ax1.xaxis.set_major_formatter(lambda x, pos: str(int(x*1000)))
    ax1.xaxis.set_major_locator(ticker.MultipleLocator(0.01))
    ax1.yaxis.set_major_locator(ticker.MultipleLocator(2000))
    ax1.margins(y=0)
    ax1.spines['top'].set_color('white')
    ax1.spines['right'].set_color('white')
    # ax1.set_yscale('log')
    # plt.ylim([1, 100000])
    # plt.yscale('log')
    fig.tight_layout()
    # plt.xlabel('Time (Second)')
    # plt.show()
    plt.savefig(f'bw_comp_canf_rs2.png', dpi=300)


if __name__ == "__main__":
    # rcParams['font.family'] = 'Times New Roman'
    # mpl.use('macosx')

    shape = 'chess'
    g = 10
    alg = 'rs'
    path = os.path.join("PATH_TO_RESULTS", f"{shape}_{alg}_g{g}")
    os.makedirs(os.path.join(path, 'processed'), exist_ok=True)
    elastic_post_process(path)

    groups = [g]
    rs = [shape]
    props_values = [groups, rs]
    combinations = list(itertools.product(*props_values))

    dfs = []

    path = os.path.join(path, "processed")
    for g in groups:
        dir_name = f"G{g}"
        subprocess.call(["mkdir", "-p", f"\"{os.path.join(path, dir_name)}\""])
        subprocess.call(f"mv {os.path.join(path, '*_G{g}_*.xlsx')} {os.path.join(path, dir_name)}", shell=True)
        dfs.append(combine_xlsx_with_formula(os.path.join(path, dir_name), rs, shape=True))

    combine_groups(path, f'summary_{shape}_{alg}_g{g}', dfs, groups, rs, 10)

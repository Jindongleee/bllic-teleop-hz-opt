#!/usr/bin/env python3
"""v3: 무명령 창에서 '팔 활동량 → 다리 반응' 전달 특성 비교.

같은 팔 활동량 구간(bin)에서 다리 떨림이 같으면 → WBC(보행체계)는 업체와 동일 반응,
차이는 입력(팔 점프 크기 = Hz) 탓. 다리 떨림이 같은 bin에서도 크면 → 보행 자체 문제.
"""
import gzip, json, glob, os, sys
import numpy as np

KNEE = [9, 10]; ANKLE_P = [11, 12]
W = 25; STRIDE = 12; CMD_EPS = 0.01

def load_frames(path):
    with gzip.open(path, 'rt') as f:
        d = json.load(f)
    frames = d['data']
    la = np.array([fr['states']['left_arm']['qpos'] for fr in frames])
    ra = np.array([fr['states']['right_arm']['qpos'] for fr in frames])
    body = np.array([fr['states']['body']['qpos'] for fr in frames])
    return np.hstack([la, ra]), body

def load_cmd_by_step(dds_path):
    opener = gzip.open if dds_path.endswith('.gz') else open
    cmds, order = {}, []
    with opener(dds_path, 'rt') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except json.JSONDecodeError: continue
            if r.get('command_type') != 'run_command': continue
            v = r['payload']['parsed']
            mag = abs(v[0]) + abs(v[1]) + abs(v[2])
            cmds[(r.get('metadata') or {}).get('step')] = mag
            order.append(mag)
    return cmds, order

def get_cmd(kind, cpath, n):
    if kind == 'vendor':
        _, order = load_cmd_by_step(cpath)
        assert len(order) == n
        return np.array(order)
    cmds, _ = load_cmd_by_step(os.path.join(cpath, 'dds_command_log.json.gz'))
    steps = sorted(int(os.path.basename(p).split('_')[-1].split('.')[0])
                   for p in glob.glob(os.path.join(cpath, 'sim_state_raw', '*.pt')))
    assert len(steps) == n
    return np.array([cmds.get(s, 0.0) for s in steps])

def windows(arm, body, cmd):
    dA = np.abs(np.diff(arm, axis=0))
    dB = np.abs(np.diff(body, axis=0))
    armjump = dA.max(axis=1)
    legjit = dB[:, KNEE + ANKLE_P].mean(axis=1)
    out = []  # (arm_mean, leg_mean) — 무명령 창만
    N = len(armjump)
    for s in range(0, N - W, STRIDE):
        e = s + W
        if cmd[s:e].max() < CMD_EPS:
            out.append((armjump[s:e].mean(), legjit[s:e].mean()))
    return np.array(out)

EPS = [
    ('업체 ep1', '/media/jindong/Data/BLLIC_2025/teleop/episode_0001/data.json.gz',
     'vendor', '/media/jindong/Data/BLLIC_2025/lerobot/dds_cmd/task-0000/episode_dds_00000001.json'),
    ('업체 ep2', '/media/jindong/Data/BLLIC_2025/teleop/episode_0002/data.json.gz',
     'vendor', '/media/jindong/Data/BLLIC_2025/lerobot/dds_cmd/task-0000/episode_dds_00000002.json'),
    ('업체 ep3', '/media/jindong/Data/BLLIC_2025/teleop/episode_0003/data.json.gz',
     'vendor', '/media/jindong/Data/BLLIC_2025/lerobot/dds_cmd/task-0000/episode_dds_00000003.json'),
    ('우리 ep0022 (18.5Hz)', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0022/data.json.gz',
     'ours', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0022'),
    ('우리 ep0026 (16.3Hz 리미터)', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0026/data.json.gz',
     'ours', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0026'),
    ('우리 ep0009 (14.8Hz)', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0009/data.json.gz',
     'ours', '/home/jindong/bllic_ws/pitcher_task/data_collect/episode_0009'),
]

BINS = [0, 0.002, 0.005, 0.010, 0.020, 0.040, 1.0]  # 창 평균 팔 |Δq| (rad)
LBL = ['<2m', '2-5m', '5-10m', '10-20m', '20-40m', '>40m']

data = {}
for name, dpath, kind, cpath in EPS:
    arm, body = load_frames(dpath)
    cmd = get_cmd(kind, cpath, len(arm))
    data[name] = windows(arm, body, cmd)

print("무명령 창에서 팔 활동량(bin, 창평균 |Δq| mrad)별 다리 떨림 중앙값 (mrad/프레임):")
print(f"{'에피소드':<26}" + ''.join(f"{l:>14}" for l in LBL))
print('-' * 110)
for name, wv in data.items():
    if not len(wv): continue
    cells = []
    for lo, hi in zip(BINS, BINS[1:]):
        m = wv[(wv[:, 0] >= lo) & (wv[:, 0] < hi)]
        cells.append(f"{np.median(m[:,1])*1e3:>7.3f}(n={len(m):>3})" if len(m) >= 3 else f"{'—':>13}")
    print(f"{name:<26}" + ''.join(f"{c:>14}" for c in cells))

print("\n팔 활동량 자체의 분포 (무명령 창 평균 팔 |Δq|, mrad):")
for name, wv in data.items():
    if not len(wv): continue
    q = np.percentile(wv[:, 0], [25, 50, 75, 95]) * 1e3
    print(f"  {name:<26} p25 {q[0]:5.2f} | med {q[1]:5.2f} | p75 {q[2]:5.2f} | p95 {q[3]:5.2f}")

#!/usr/bin/env python3
"""수집 세션 중 코어 경합 모니터 (읽기 전용, P1-1 1-1용).

teleop.py(sim)·xr 계열(C) 프로세스를 자동 탐지해 5초 간격으로
스레드별 CPU%·코어 배치·시스템 load를 JSONL로 기록한다.

사용:  python3 contention_monitor.py            # Ctrl+C로 종료
출력:  contention_YYYYmmdd_HHMMSS.jsonl (이 디렉터리)
분석:  python3 contention_monitor.py --report <jsonl>
"""
import json, os, sys, time, glob
from datetime import datetime

INTERVAL = 5.0
HZ = os.sysconf('SC_CLK_TCK')

def find_pids():
    out = {}
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            with open(p, 'rb') as f:
                cmd = f.read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        pid = int(p.split('/')[2])
        if 'teleop.py' in cmd and '--generate_data' in cmd:
            out.setdefault('sim', (pid, cmd[:160]))  # 부모(먼저 뜬 쪽)가 메인
        elif any(k in cmd for k in ('tv_wrapper', 'xr_teleop', 'teleop_hand', 'image_server')):
            out[f'c_{pid}'] = (pid, cmd[:160])
    return out

def sample_threads(pid):
    base = f'/proc/{pid}/task'
    out = {}
    try:
        tids = os.listdir(base)
    except OSError:
        return None
    for tid in tids:
        try:
            with open(f'{base}/{tid}/stat') as f:
                s = f.read()
            rp = s.rindex(')')
            comm = s[s.index('(') + 1:rp]
            fs = s[rp + 2:].split()
            out[tid] = (comm, int(fs[11]) + int(fs[12]), int(fs[36]))
        except OSError:
            pass
    return out

def monitor():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'contention_{ts}.jsonl')
    print(f'[monitor] 기록: {path}  (Ctrl+C로 종료)')
    prev = {}
    with open(path, 'w') as out:
        while True:
            pids = find_pids()
            t0 = time.time()
            cur = {name: sample_threads(pid) for name, (pid, _) in pids.items()}
            rec = {'t': datetime.now().isoformat(timespec='seconds'),
                   'load': os.getloadavg(), 'procs': {}}
            for name, threads in cur.items():
                if threads is None:
                    continue
                rows = []
                pv = prev.get(name, ({}, t0))
                dt = t0 - pv[1]
                if dt > 0 and pv[0]:
                    for tid, (comm, cpu, psr) in threads.items():
                        if tid in pv[0]:
                            d = (cpu - pv[0][tid][1]) / HZ / dt * 100
                            if d > 1.0:
                                rows.append([comm, round(d, 1), psr])
                rows.sort(key=lambda r: -r[1])
                rec['procs'][name] = {'pid': pids[name][0], 'cmd': pids[name][1], 'nthreads': len(threads),
                                      'busy': rows[:20],
                                      'total': round(sum(r[1] for r in rows), 1)}
                prev[name] = (threads, t0)
            out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush()
            tot = ' '.join(f"{k}:{v['total']}%" for k, v in rec['procs'].items())
            print(f"[{rec['t']}] load {rec['load'][0]:.1f} | {tot or '(프로세스 없음)'}")
            time.sleep(INTERVAL)

def report(path):
    import statistics
    from collections import defaultdict
    per = defaultdict(lambda: defaultdict(list))  # proc -> comm -> [cpu%]
    loads, totals = [], defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        loads.append(r['load'][0])
        for name, p in r['procs'].items():
            totals[name].append(p['total'])
            agg = defaultdict(float)
            for comm, cpu, psr in p['busy']:
                agg[comm] += cpu
            for comm, cpu in agg.items():
                per[name][comm].append(cpu)
    print(f"샘플 {len(loads)}개 | load avg 중앙 {statistics.median(loads):.2f}")
    for name, comms in per.items():
        print(f"\n== {name} (프로세스 합 중앙 {statistics.median(totals[name]):.0f}%) ==")
        rows = sorted(comms.items(), key=lambda kv: -statistics.median(kv[1]))
        for comm, vals in rows[:15]:
            print(f"  {comm:<22} med {statistics.median(vals):6.1f}%  max {max(vals):6.1f}%  (n={len(vals)})")

if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--report':
        report(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == '--report':
        files = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contention_*.jsonl')))
        report(files[-1])
    else:
        try:
            monitor()
        except KeyboardInterrupt:
            print('\n[monitor] 종료')

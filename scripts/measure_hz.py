#!/usr/bin/env python3
"""텔레옵 수집 Hz 측정 — 올바른 지표로.

왜 이 스크립트가 필요한가
------------------------
teleop.py가 찍는 `overall average frequency`는 세션 전체(대부분 유휴 대기)의 평균이라
실제 조종 중 성능을 반영하지 않는다. 8/7 세션 실측: overall 24.6Hz vs moving 13.8Hz (1.7배 차이).
8/3~8/7의 A/B 실험이 overall로 비교됐다면 결론이 무효일 수 있다.

★ 최종 지표 (2026-08-11 확정): **녹화 dt** — 실제로 저장된 프레임들 사이의 시간 간격
   구하는 법: dds 로그의 `metadata.step` ↔ `sim_state_raw/sim_state_XXXXXX.pt`의 step 을 조인해
   **저장된 연속 프레임 쌍의 relative_time 차이**만 모아 평균. 가정 0, 유휴 0.
   업체는 녹화율 100%(run_command 5034 = 프레임 5034)라 세션 평균 34.4ms가 곧 녹화 dt →
   우리 값과 같은 잣대로 직접 비교된다.

⚠️ 여기까지 오는 데 지표를 세 번 틀렸다 (2026-08-10~11)
   ① 세션 전체 평균 → 유휴가 섞임. 녹화 비중이 다르면 런 간 비교 불가
   ② prof 소계(물리+렌더+저장) → **계측된 3항목의 합일 뿐 실제 루프가 아님**.
      실제 루프엔 항상 ~13ms의 미계측 오버헤드가 깔려 있어 Hz를 24.9로 과대평가했다
   ③ 미계측 역산 → 저장 배리어·씬 리셋 스톨이 섞여 앞뒤가 안 맞았다(T2 6.2 vs T6 11.5ms)
   → ④ step 조인이 답. 아래 `rec_dt()`.

⚠️ 중앙값을 쓰면 안 된다 (2026-08-10 발견)
   간격 분포가 **이봉형(bimodal)**이다. render_interval=2 때문에 렌더 없는 스텝과 있는 스텝이
   번갈아 나오며 두 개의 봉우리를 만든다.
     업체: ~16ms(렌더X) / ~50ms(렌더O)  → 중앙값 46.3ms(21.6Hz), 평균 34.4ms(29.1Hz)
     우리: ~40ms(렌더X) / ~85ms(렌더O)  → 중앙값 59.2ms(16.9Hz), 평균 72.7ms(13.8Hz)
   중앙값은 어느 쪽 봉우리에 걸리느냐에 따라 요동쳐서 두 분포를 비교할 수 없다.
   "조종자의 1초당 몇 프레임을 담았나"가 우리가 알고 싶은 값이고, 그건 정확히 평균(n/span)이다.

사용법
------
  python3 measure_hz.py                    # data_collect의 최신 에피소드
  python3 measure_hz.py episode_0010       # 특정 에피소드
  python3 measure_hz.py --all              # 전부 나열 (A/B 비교용)
  python3 measure_hz.py --log sim_ep0.log  # + 시뮬 로그의 prof/Hz 통계까지

참조: 옵시디언 "09 텔레옵 수집 Hz 규명/01 Hz 점검 체크리스트" A-1
"""
import argparse
import glob
import gzip
import json
import os
import re
import statistics
import sys

DATA_DIR = os.path.expanduser("~/bllic_ws/pitcher_task/data_collect")


def rec_dt(ep_dir):
    """★ 대표 지표: 저장된 연속 프레임 쌍의 간격(ms) 배열.

    dds 로그 run_command 의 metadata.step 과 sim_state_raw/*.pt 의 step 을 조인한다.
    연속(step, step+1)인 쌍만 사용 — 녹화를 잠깐 멈춘 구간의 큰 gap이 섞이지 않는다.
    """
    import numpy as np
    tm = {}
    dds = os.path.join(ep_dir, "dds_command_log.json.gz")
    if not os.path.isfile(dds):
        return np.array([])
    with gzip.open(dds, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("command_type") != "run_command":
                continue
            st = (r.get("metadata") or {}).get("step")
            t = r.get("relative_time")
            if isinstance(st, int) and isinstance(t, (int, float)):
                tm[st] = t
    steps = []
    for p in glob.glob(os.path.join(ep_dir, "sim_state_raw", "*.pt")):
        n = os.path.basename(p).split("_")[-1].split(".")[0]
        try:
            steps.append(int(n))
        except ValueError:
            pass
    steps.sort()
    d = [tm[b] - tm[a] for a, b in zip(steps, steps[1:])
         if b == a + 1 and a in tm and b in tm and tm[b] > tm[a]]
    return np.asarray(d) * 1000.0

# 비교 기준선 (옵시디언 "02 Hz 실측 기록" §1)
BASELINE = {          # 전부 ★녹화 dt 기준 (2026-08-11 재측정)
    "업체 원본 (커피 ep1)": (29.10, 34.4),
    "우리 8/7 (ep0009)":   (14.76, 67.8),   # 개선 전
    "우리 현재 (ep0014)":   (18.69, 53.5),   # 카메라OFF + 캐싱OFF + USD캐싱
}


def load_dds(path):
    """dds_command_log.json.gz는 gzip JSONL이다 (json.load()로는 못 읽음)."""
    by = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = r.get("relative_time")
            if isinstance(t, (int, float)):
                by.setdefault(r.get("command_type", "?"), []).append(t)
    return by


def analyse(ts):
    """간격 통계. ★ 대표 지표는 평균(=n/span=처리량). 중앙값은 분포 모양 참고용."""
    if len(ts) < 10:
        return None
    ts = sorted(ts)
    dts = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not dts:
        return None
    span = ts[-1] - ts[0]
    srt = sorted(dts)
    mean = statistics.mean(dts)
    # 이봉 분해: 중앙값 기준으로 빠른 봉 / 느린 봉 (render_interval=2의 렌더X / 렌더O)
    med = statistics.median(dts)
    fast = [d for d in dts if d < med]
    slow = [d for d in dts if d >= med]
    return {
        "n": len(ts),
        "span": span,
        "hz": 1.0 / mean,                                    # ★ 대표 지표
        "hz_median": 1.0 / med,                              # 참고 (이봉이라 왜곡됨)
        "dt_mean_ms": mean * 1000,
        "dt_med_ms": med * 1000,
        "dt_p10_ms": srt[int(len(srt) * 0.10)] * 1000,
        "dt_p90_ms": srt[int(len(srt) * 0.90)] * 1000,
        "fast_ms": statistics.median(fast) * 1000 if fast else 0,
        "slow_ms": statistics.median(slow) * 1000 if slow else 0,
    }


def report_episode(ep_dir, verbose=True):
    dds = os.path.join(ep_dir, "dds_command_log.json.gz")
    if not os.path.isfile(dds):
        print(f"  ⚠ dds_command_log.json.gz 없음: {ep_dir}")
        return None
    by = load_dds(dds)
    if "run_command" not in by:
        print(f"  ⚠ run_command 없음 (types: {list(by)})")
        return None

    st = analyse(by["run_command"])
    if st is None:
        print(f"  ⚠ 샘플 부족: {ep_dir}")
        return None

    name = os.path.basename(ep_dir.rstrip("/"))
    frames = None
    dj = os.path.join(ep_dir, "data.json.gz")
    if os.path.isfile(dj):
        try:
            frames = len(json.load(gzip.open(dj, "rt"))["data"])
        except Exception:
            pass

    rd = rec_dt(ep_dir)
    if verbose:
        print(f"\n{'='*66}\n  {name}\n{'='*66}")
        if len(rd) >= 30:
            import numpy as _np
            print(f"  ★ 녹화 dt (저장 프레임 간) : {1000/rd.mean():6.2f} Hz   ({rd.mean():.1f} ms, n={len(rd)})")
            print(f"     p50/p90                : {_np.median(rd):.1f} / {_np.percentile(rd,90):.1f} ms")
        else:
            print(f"  ★ 녹화 dt : 측정 불가 (연속 쌍 {len(rd)}개 — sim_state_raw 없거나 부족)")
        print(f"  ─ 참고 ─ 세션 전체 평균     : {st['hz']:6.2f} Hz   ({st['dt_mean_ms']:.1f} ms)  ← 유휴 섞임, 런 간 비교 금지")
        print(f"    run_command 수 / 구간   : {st['n']} / {st['span']:.1f}s")
        if frames:
            print(f"    저장 프레임 수          : {frames}")

        # ★ 아래 모든 환산은 '녹화 구간' dt로 한다 (2026-08-12 버그픽스).
        #   예전엔 st['hz'](세션 전체 = 유휴 포함)를 썼다. 그래서 유휴가 길수록 부풀림이
        #   좋아 보이는 역설이 생겼다 — ep0027(유휴 많음) 1.79배 vs ep0028(유휴 0초) 2.59배로
        #   개선된 런이 더 나빠 보였다. 실제로는 rec 기준 2.66 → 2.59로 개선이 맞다.
        rec_ms = float(rd.mean()) if len(rd) >= 30 else None
        rec_hz = 1000.0 / rec_ms if rec_ms else None

        print(f"\n  ── 이봉 분해 (세션 전체 dt 기준 — 유휴 섞임 주의) ──")
        print(f"    빠른 봉 (렌더 X)        : {st['fast_ms']:6.1f} ms")
        print(f"    느린 봉 (렌더 O)        : {st['slow_ms']:6.1f} ms")
        print(f"    → 렌더 호출 1회 비용    : {st['slow_ms'] - st['fast_ms']:6.1f} ms")
        print(f"    중앙값 {st['dt_med_ms']:.1f}ms ({st['hz_median']:.2f}Hz) ← 이봉이라 비교에 쓰지 말 것")
        print(f"    p10/p90                 : {st['dt_p10_ms']:.1f} / {st['dt_p90_ms']:.1f} ms")

        if rec_hz is None:
            print(f"\n  ── 비교/시간축 왜곡 : 녹화 dt 부족으로 생략 ──")
            return st

        print(f"\n  ── 비교 (★ 녹화 dt 기준) ──")
        for label, (hz, _) in BASELINE.items():
            ratio = rec_hz / hz
            mark = "🟢" if ratio >= 0.98 else ("🟡" if ratio >= 0.85 else "🔴")
            print(f"    {mark} {label:<22} {hz:5.2f} Hz  → 우리 대비 {ratio:5.2f}배")

        # 시간축 왜곡 환산 — 전부 녹화 dt 기준
        sim_dt_ms = 20.0   # sim.dt=0.005 × range(4)
        print(f"\n  ── 시간축 왜곡 (★ 녹화 dt 기준) ──")
        print(f"    프레임당 동작량 부풀림  : 평균 {rec_ms/sim_dt_ms:.2f}배")
        print(f"    fps:30 재생 시 배속     : {30.0 / rec_hz:.2f}배")
        if frames:
            print(f"    조종자 실제 시간(녹화)  : {frames * rec_ms / 1000:.1f}s")
            print(f"    시뮬 물리시간           : {frames * sim_dt_ms / 1000:.1f}s")
            print(f"    fps:30 재생 길이        : {frames / 30:.1f}s")
        print(f"    → 올바른 fps 라벨       : {rec_hz:.1f}  (현재 30으로 박혀 있음)")
    return st


def report_log(log_path):
    """시뮬 로그에서 prof 분해 + overall/moving 괴리 확인."""
    if not os.path.isfile(log_path):
        print(f"  ⚠ 로그 없음: {log_path}")
        return
    prof, overall, moving = [], [], []
    pat = re.compile(r"물리4스텝 ([\d.]+)ms .* 렌더\+obs ([\d.]+)ms .* 상태수집·저장 ([\d.]+)ms")
    with open(log_path, errors="ignore") as f:
        for line in f:
            m = pat.search(line)
            if m:
                prof.append(tuple(float(g) for g in m.groups()))
            elif "overall average frequency" in line:
                overall.append(float(line.split(":")[1].split("Hz")[0]))
            elif "moving average frequency" in line:
                moving.append(float(line.split(":")[1].split("Hz")[0]))

    print(f"\n{'='*66}\n  {os.path.basename(log_path)}\n{'='*66}")
    print("  ⚠️ 유휴 구간 수치는 판단에 쓰지 말 것 (2026-08-11 사용자 지시).")
    print("     렌더·캐싱은 '움직일 때' 비용이 전혀 다르다. 결론은 항상 녹화 구간으로.")
    if prof:
        ph = statistics.median(p[0] for p in prof)
        rd = statistics.median(p[1] for p in prof)
        sv = statistics.median(p[2] for p in prof)
        tot = ph + rd + sv
        print(f"  [prof-sim] 중앙값 (n={len(prof)})")
        print(f"    물리 4스텝    {ph:6.1f} ms")
        print(f"    렌더+obs      {rd:6.1f} ms")
        print(f"    상태수집·저장 {sv:6.1f} ms")
        print(f"    ─────────────────────")
        print(f"    소계          {tot:6.1f} ms  → {1000/tot:.1f} Hz")
    if overall and moving:
        o, mv = statistics.median(overall), statistics.median(moving)
        print(f"\n  (참고) teleop.py 자체 통계 overall {o:.2f} / moving {mv:.2f} Hz")
        print(f"    🚫 둘 다 판단 근거로 쓰지 말 것. overall=유휴 포함, moving=최근 100루프라 흔들림.")
        if prof:
            print(f"    → moving({1000/mv:.1f}ms) − 소계({tot:.1f}ms) = 미분해 {1000/mv - tot:.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode", nargs="?", help="에피소드 이름 또는 경로 (생략 시 최신)")
    ap.add_argument("--all", action="store_true", help="전부 요약 (A/B 비교용)")
    ap.add_argument("--log", help="시뮬 로그 파일 (prof 분해)")
    ap.add_argument("--dir", default=DATA_DIR)
    args = ap.parse_args()

    eps = sorted(glob.glob(os.path.join(args.dir, "episode_*")))
    if not eps:
        sys.exit(f"에피소드 없음: {args.dir}")

    if args.all:
        hdr = (f"{'에피소드':<16}{'★녹화Hz':>10}{'녹화dt':>9}"
               f"{'세션Hz':>8}{'프레임':>8}{'부풀림':>8}{'30fps':>8}")
        print(hdr); print("-" * 78)
        for ep in eps:
            st = report_episode(ep, verbose=False)
            if not st:
                continue
            frames = "-"
            dj = os.path.join(ep, "data.json.gz")
            if os.path.isfile(dj):
                try:
                    frames = len(json.load(gzip.open(dj, "rt"))["data"])
                except Exception:
                    pass
            rd = rec_dt(ep)
            if len(rd) >= 30:
                rhz, rms = 1000 / rd.mean(), rd.mean()
                print(f"{os.path.basename(ep):<16}{rhz:>10.2f}{rms:>8.1f}ms{st['hz']:>8.2f}"
                      f"{str(frames):>8}{rms/20:>7.2f}x{30/rhz:>7.2f}x")
            else:
                print(f"{os.path.basename(ep):<16}{'—':>10}{'—':>10}{st['hz']:>8.2f}"
                      f"{str(frames):>8}{'—':>8}{'—':>8}")
        print("-" * 78)
        print("-" * 78)
        for label, (hz, dt) in BASELINE.items():
            print(f"{label:<16}{hz:>10.2f}{dt:>8.1f}ms{'':>8}{'':>8}{dt/20:>7.2f}x{30/hz:>7.2f}x")
    else:
        if args.episode:
            ep = args.episode if os.path.isdir(args.episode) else os.path.join(args.dir, args.episode)
        else:
            ep = max(eps, key=os.path.getmtime)
        report_episode(ep)

    if args.log:
        lg = args.log if os.path.isfile(args.log) else os.path.join(args.dir, args.log)
        report_log(lg)


if __name__ == "__main__":
    main()

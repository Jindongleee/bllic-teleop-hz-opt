# 적용 절차 (받는 쪽 Claude용)

> 전제: 당신(받는 쪽)의 `etri_eai_sim-main`은 **2026-08-07 시점 스냅샷**이다.
> 이 패키지의 `files/`는 그 시점 이후 바뀐 **파일 7개의 최신 전체본**이다 (경로 동일).
> 배경·원리·측정법은 `HANDOFF_teleop_hz_개선_인수인계.md`를 먼저 읽을 것.

## 1단계 — 델타 파일 7개 반영

| 파일 (etri_eai_sim-main/ 기준) | 담긴 개선 | 비고 |
|---|---|---|
| `teleop.py` | ⑥ `[prof-main]`·`[prof-loop]` 계측, `_PROF` 게이트 | 메인 루프 계측 |
| `action_provider/action_provider_wh_dds.py` | ② USD 인덱스 캐싱(`SCENE_INDEX_CACHE`, 기본 ON) · ③ `RENDER_INTERVAL` env 게이트 · ⑤ `ARM_RATE_LIMIT` · ⑥ `[prof-sim]`·`[prof-save]`·`[prof-worker]` · 녹화 게이트(`RECORD_CTRL_MODE`) | **핵심 파일.** 기각된 `SAVE_WORKER_PROC` 코드도 있으나 기본 OFF·무해 |
| `action_provider/save_worker_proc.py` | (신규 파일) 기각된 실험의 자식 스크립트 | 기본 미사용. 같이 복사 (import 오류 방지) |
| `tasks/common_config/camera_configs.py` | ① `TELEOP_NO_IMAGE_STREAM`·`TELEOP_VIEWCAM_RES` 카메라 게이트 | |
| `tasks/common_observations/camera_state.py` | ① shm 비동기 기록 차단 게이트 | |
| `render_final.py` | 오프라인 렌더 개선 (headless 대응 등) | 렌더 파이프라인 쓸 때만 필요 |
| `eval_sim.py` | 위 게이트들의 eval 쪽 반영 | eval 쓸 때만 필요 |

**적용 방법 (중요)**:
1. 먼저 자기 트리에서 `git status`/수정 여부 확인 — **8/7 이후 자기가 손댄 파일과 겹치는지** 체크.
2. 안 겹치면: `files/`의 파일을 그대로 덮어쓰기 (drop-in).
3. 겹치면: `diff -u <자기파일> <패키지파일>`로 보고 병합. 이 패키지 파일이 "정답 상태"다.
4. 문법 확인: `python3 -c "import ast; ast.parse(open('<파일>').read())"`

## 2단계 — vuer 라이브러리 패치 (④, 별도 필수)

sim 저장소가 아니라 **C 쪽 conda env의 site-packages** 대상. `vuer_uplink_busyspin.patch` 참조.

```bash
V=$(python -c "import vuer, os; print(os.path.dirname(vuer.__file__))")/server.py   # tv env에서
cp "$V" "$V.bak_$(date +%Y%m%d)"
# patch -p0 경로가 다를 것이므로 수동 적용 권장: uplink 코루틴의
#   else: await sleep(0.0)   ← 이 한 줄만 (vuer 0.0.32RC7 기준 :1125)
# → await sleep(0.002) 로 변경. 다른 sleep(0.0) 두 곳은 건드리지 말 것.
```
검증: 조종 중 televuer 자식 프로세스 CPU가 100% → 5% 이하로 떨어지면 성공.

## 3단계 — 실행 환경변수 (코드가 아니라 기동 시 지정)

```bash
# 수집 기동 (권장 조합 전체)
PROF=1 RENDER_INTERVAL=3 TELEOP_HEADCAM_ONLY=1 TELEOP_NO_IMAGE_STREAM=1 \
TELEOP_VIEWCAM_RES=1 ARM_RATE_LIMIT=1 RECORD_CTRL_MODE=1 python teleop.py ...
# C 쪽
STREAM_VR_VIDEO=0 python teleop_hand_and_arm.py ...
```
`scripts/collect_episode.sh`·`start_teleop_c.sh`는 **우리 태스크 전용 경로가 박혀 있으므로 참고용** (env 배선·설정 지문 기록·좀비 가드 패턴을 베끼면 됨).

## 4단계 — 검증 (필수 3종)

1. 짧은 녹화 1회 → `data.json.gz` 프레임 키·`states` 구조가 기존과 동일한지, `sim_state_raw/*.pt` 개수 = 프레임 수인지
2. 그 에피소드를 `render_final.py`로 완주 (렌더 파이프라인 쓰는 경우)
3. Hz 측정: **저장 프레임 ÷ REC 시간** (`scripts/measure_hz.py` 참고, 경로 상수만 수정)

## 동봉 스크립트 (scripts/)

| 파일 | 용도 |
|---|---|
| `measure_hz.py` | ★Hz 측정·에피소드 비교 (DATA_DIR 상수 수정 필요) |
| `contention_monitor.py` | 수집 중 프로세스/스레드별 CPU 경합 모니터 (읽기 전용) |
| `analyze_shake_transfer.py` | 헤드캠 흔들림 원인 판별 (팔 활동량 bin 매칭) — 경로 수정 필요 |
| `collect_episode.sh` / `start_teleop_c.sh` | 기동 스크립트 참고용 (경로 우리 것) |

## C 쪽(xr_teleoperate)은?

**8/7 이후 코드 변경 없음** — 당신의 zip 그대로 유효. 필요한 건 vuer 패치(2단계)와 `STREAM_VR_VIDEO=0`뿐.

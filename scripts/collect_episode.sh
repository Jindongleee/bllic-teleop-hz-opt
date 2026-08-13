#!/bin/bash
# 쓰러진 물병 세우기 — 스킬단위 수집 (터미널 A: 시뮬)
# 사용법: ./collect_episode.sh <씬 번호 0-49>
#
# 새 방식(2026-07-27, 스킬단위 자동화):
#   - 종료·저장은 done-file이 아니라 record_ctrl finish 이벤트(왼손 그립)가 sim 내부에서 처리.
#   - 시뮬을 포그라운드로 띄운다. 한 번의 부팅 = move→stand→pick→place 한 에피소드
#     (스킬 실패 시 오른손X→그립으로 그 스킬 시작점 복귀·재시도, 재부팅 불필요).
#   - [v2 주의] 왼손 그립(finish)으로 저장돼도 C는 종료되지 않고 IDLE로 다음 에피소드를 대기함(MULTI_EPISODE=1).
#     C 세션 종료는 오른손 A버튼 또는 C 터미널에서 Ctrl+C — 안 끄고 새로 띄우면 이중발행 사고(2026-08-05) 재발.
set -e
i=${1:?사용법: ./collect_episode.sh <0-49>}

SCENE_FILE="$HOME/bllic_ws/pitcher_task/scenes/fallen_pitcher_instance_${i}.json"
DATA_DIR="$HOME/bllic_ws/pitcher_task/data_collect"   # 2026-08-04부터: 디버깅/테스트용 episode_0001~0024가 쌓인 data/와 분리, 실제 수집분만 여기에
[ -f "$SCENE_FILE" ] || { echo "씬 파일 없음: $SCENE_FILE (generate_fallen_scenes.py 먼저 실행)"; exit 1; }
mkdir -p "$DATA_DIR"

source "$HOME/bllic_ws/venv_sim/bin/activate"
export OMNI_KIT_ACCEPT_EULA=YES
# 2026-08-10: 파이썬 stdout이 tee로 파이프되면 블록 버퍼링돼 [prof-sim]/[prof-save] 출력이
# 버퍼에 갇혔다가 프로세스 종료 시 유실된다 (T1 런에서 녹화 구간 prof 로그 통째로 소실).
# 터미널 C 스크립트엔 원래 있던 설정. 측정 신뢰성을 위해 A에도 추가.
export PYTHONUNBUFFERED=1
# 텔레옵은 창(좌클릭)이 필요 → 디스플레이 달린 GPU 1에서만 렌더 가능. GPU 0(무디스플레이)은 swapchain 실패.
# 따라서 텔레옵=GPU1(기본), 타 세션 헤드리스 eval/render=GPU0 배치. (CUDA_VISIBLE_DEVICES=0 시도 → 그래픽 초기화 실패로 되돌림, 2026-07-28)
export LD_LIBRARY_PATH="$HOME/bllic_ws/cyclonedds-install/lib"
export CURRENT_SCENE_FILE="$SCENE_FILE"   # Priority 1 — 공식 에셋 무수정으로 커스텀 씬 로드
export RECORD_CTRL_MODE=1                 # 첫 그립 전 자동녹화 방지(리드인 프레임 제거)
export MULTI_EPISODE=1                     # finish 후 재부팅 없이 다음 에피소드(v2)
# ── 카메라 파이프라인 ──────────────────────────────────────────────────────────
# 2026-08-10: 조종자가 **Isaac Sim 3인칭 뷰포트만** 보고 조종함을 확인(헤드셋은 STREAM_VR_VIDEO=0
# 패스스루, 모니터에도 헤드캠 창 없음). 그런데 이미지 경로는 전 구간이 그대로 돌고 있었다:
#   sim 카메라 렌더 → camera_image ObsTerm → GPU→CPU 복사 → /dev/shm
#     → image_server(터미널 B) → ZMQ → teleop C의 ImageClient 스레드 → tv_img_shm
#     → TeleVuerWrapper(stream_video=False)에서 **버려짐**
# (teleop_hand_and_arm.py:169의 ImageClient 스레드는 STREAM_VR_VIDEO 플래그를 읽기 전에 무조건 시작됨)
# 즉 소비자가 0인데 터미널 3개가 이 일에 CPU를 쓰는 중 → TELEOP_NO_CAMERAS로 전체 차단 실험.
#
#   TELEOP_NO_CAMERAS=1 ./collect_episode.sh N     ← 카메라 프림 자체를 안 만듦 (터미널 B 띄우지 말 것)
#
# 안전성 확인(2026-08-10 코드검증): ① 관측그룹 concatenate_terms=False라 ObsTerm 제거해도 정책 shape 불변
# ② camera_image 반환값은 placeholder이고 코드 전체에서 소비처 0건 ③ 저장 데이터는 colors={}라 영향 없음
# ④ Isaac Sim 뷰포트는 sim.render()라 카메라 프림과 무관 — 3인칭 화면은 그대로 남음
# ⑤ image_server 미기동 시 C의 ImageClient는 데몬 스레드에서 recv() 블록만 함(멈춤·크래시 없음)
# ⑥ render_final.py는 별도 env를 새로 띄우므로 오프라인 렌더 무영향
# 기본값은 기존과 동일(TELEOP_HEADCAM_ONLY=1) — 아무것도 안 넘기면 8/7까지의 동작 그대로.
if [ -n "${TELEOP_NO_CAMERAS:-}" ]; then
  export TELEOP_NO_CAMERAS
  echo "  [실험] TELEOP_NO_CAMERAS=1 — 카메라 프림 전부 제거. 조종은 Isaac Sim 3인칭 뷰포트로."
  echo "         ⚠ 터미널 B(image_server)는 띄우지 마세요 (shm이 생성되지 않음)."
else
  export TELEOP_HEADCAM_ONLY="${TELEOP_HEADCAM_ONLY:-1}"   # 헤드캠만 렌더, 손목캠 2개 제거 (2026-08-03)
fi
# quality 모드 = rtx.raytracing.cached.enabled=true(레이트레이싱 캐싱)까지 포함하는 프리셋 묶음
# (IsaacLab/apps/rendering_modes/quality.kit, performance.kit은 false). 2026-07-23엔 quality가
# 제어루프를 4.8Hz로 떨어뜨려 performance 유지했으나, 이후 STREAM_VR_VIDEO=0·TELEOP_HEADCAM_ONLY로
# Hz 병목을 해소했으므로 2026-08-06 재실험 겸 quality로 전환.
# ${RENDER_MODE:-quality}: 기본값은 quality지만, 호출 전에 RENDER_MODE=performance처럼 넘기면
# 그 값을 존중한다 (2026-08-06 수정 — 예전엔 무조건 quality로 덮어써서 override가 씹혔음).
# 2026-08-07 확정: performance + 레이트레이싱 캐싱만 true (어제 A/B 실험 최고 성적 조합, overall 17.5Hz).
# quality 전체를 켤 필요 없이 캐싱 하나가 속도 이득의 대부분이었음. 캐싱은 EXTRA_KIT_ARGS로 주입.
export RENDER_MODE="${RENDER_MODE:-performance}"
# ⚠️ 2026-08-10 버그픽스: `${VAR:-기본값}`의 `:-`는 **미설정과 빈 문자열을 똑같이 취급**한다.
#    그래서 `EXTRA_KIT_ARGS="" ./collect_episode.sh 0`(캐싱 끄기)을 해도 기본값이 되살아나
#    캐싱이 계속 켜진 채로 돌았다 (P3_nortcache 런이 이 함정에 걸림).
#    `${VAR-기본값}`(콜론 없음)은 **미설정일 때만** 기본값을 쓰고 빈 문자열은 그대로 존중한다.
#    → 캐싱 끄기: `EXTRA_KIT_ARGS="" ./collect_episode.sh 0`
export EXTRA_KIT_ARGS="${EXTRA_KIT_ARGS---/rtx/raytracing/cached/enabled=true}"

# [2026-08-11] 헤드캠 render product 해상도.
#   TELEOP_NO_IMAGE_STREAM=1 일 때만 camera_configs 가 참조한다(아무도 안 읽는 render product 축소용).
#   ep0022(T12) 이후 기준 설정은 1x1. 스크립트에 기본값이 없어서 T15 때 64로 떨어진 적 있음 → 여기 고정.
#   ⚠️ ${VAR-} 형식(: 없음)을 쓸 것. `TELEOP_VIEWCAM_RES=""` 를 넘겨도 기본값이 되살아나지 않게.
export TELEOP_VIEWCAM_RES="${TELEOP_VIEWCAM_RES-1}"

# [2026-08-12] 뷰포트 렌더 주기 (action_provider가 직접 읽는다).
#   ep0026 기준 렌더 1회 = 33ms. interval=2면 스텝당 16.5ms, 3이면 11ms → 프레임 −5ms 기대.
#   대가: 조종 화면 갱신이 12Hz→8Hz로 끊긴다. 조종 가능한지가 채택 기준.
#   ⚠️ teleop.py의 --render_interval 인자는 죽어 있다(파싱만 함). 반드시 이 환경변수로 줄 것.
#   사용: RENDER_INTERVAL=3 RUN_NOTE=T17_ri3 ./collect_episode.sh 0
export RENDER_INTERVAL="${RENDER_INTERVAL-2}"

# ── [2026-08-12] 기준 설정 고정 ────────────────────────────────────────────────
# ep0027(T17) 사고: RENDER_INTERVAL 하나만 바꿀 생각이었는데 지문을 보니 3개가 더 바뀌어 있었다.
# 원인 = 이 셋이 스크립트에 기본값 없이 **다른 세션의 셸 export**로만 살아 있었고,
#        새 터미널에서 돌리자 전부 미설정으로 되돌아감 (T15의 VIEWCAM_RES 1→64 사고와 동일 패턴).
# 기준선(ep0026)을 스크립트가 스스로 보장하도록 여기에 박는다. 끄려면 `VAR="" ./collect_episode.sh`.
#
#   TELEOP_NO_IMAGE_STREAM: ⚠ 이게 1이 아니면 위 TELEOP_VIEWCAM_RES=1이 **무시된다**
#                           (camera_configs.py 가 이 플래그 안에서만 해상도를 읽음) → 헤드캠 원해상도로 복귀
#   ARM_RATE_LIMIT        : 팔 관절 프레임당 속도 상한 (T16에서 도입)
#   PROF                  : [prof-sim] 물리/렌더 분해 출력. 실측 오버헤드 0.001% 라 항상 켜둔다
export TELEOP_NO_IMAGE_STREAM="${TELEOP_NO_IMAGE_STREAM-1}"
export ARM_RATE_LIMIT="${ARM_RATE_LIMIT-1}"
export PROF="${PROF-1}"
# physics dt 실험 결과 (2026-08-07): 업체 시간축(1/120=33.3ms/프레임) 정합을 시도했으나
# **걷기 불안정으로 폐기** — Isaac 납품판 policy.onnx·PD게인·지연버퍼·접촉솔버가 전부 dt=5ms
# (20ms 제어주기) 전제로 튜닝돼 있어 33.3ms에서 균형이 무너짐. OmniGibson 30Hz 구동과는
# 물리 튜닝이 다른 세계라 dt만 바꿔선 정합 불가. 기본 0.005(20ms/프레임) 유지.
# (env cfg의 PHYSICS_DT 게이트는 살려둠 — 필요 시 명시적으로 넘겨 재실험 가능)

# 2026-08-10: 런마다 sim_ep0.log를 덮어써서 P0 로그가 날아갔다. RUN_NOTE를 파일명에 넣어 보존.
if [ -n "${RUN_NOTE:-}" ]; then
  SIM_LOG="$DATA_DIR/sim_${RUN_NOTE}.log"
else
  SIM_LOG="$DATA_DIR/sim_ep${i}.log"
fi

# ── 설정 지문 기록 (2026-08-10) ────────────────────────────────────────────────
# ep0007(렌더X 19ms)과 ep0009(43ms)가 왜 2.3배 차이났는지 사후에 알 수 없었던 이유 =
# 어떤 설정으로 돌렸는지 로그에 안 남았기 때문. 이제 에피소드 폴더 옆에 지문을 남긴다.
CFG_FINGERPRINT=$(cat <<EOF
{"ts":"$(date -Iseconds)","scene":${i},
 "RENDER_MODE":"${RENDER_MODE}","EXTRA_KIT_ARGS":"${EXTRA_KIT_ARGS}",
 "TELEOP_NO_CAMERAS":"${TELEOP_NO_CAMERAS:-}","TELEOP_HEADCAM_ONLY":"${TELEOP_HEADCAM_ONLY:-}",
 "PHYSICS_DT":"${PHYSICS_DT:-default(0.005)}","SIM_PHYSICS_DEVICE":"${SIM_PHYSICS_DEVICE:-default(cpu)}",
 "SKIP_SIM_STATE_RAW":"${SKIP_SIM_STATE_RAW:-}","TELEOP_NO_IMAGE_STREAM":"${TELEOP_NO_IMAGE_STREAM:-}","TELEOP_VIEWCAM_RES":"${TELEOP_VIEWCAM_RES}","RENDER_INTERVAL":"${RENDER_INTERVAL}",
 "PROF":"${PROF:-}","ARM_RATE_LIMIT":"${ARM_RATE_LIMIT:-}","ARM_RATE_LIMIT_SCALE":"${ARM_RATE_LIMIT_SCALE:-}",
 "RECORD_CTRL_MODE":"${RECORD_CTRL_MODE}","PIN_CORES":"${PIN_CORES:-}",
 "MULTI_EPISODE":"${MULTI_EPISODE}","note":"${RUN_NOTE:-}"}
EOF
)
echo "$CFG_FINGERPRINT" > "$DATA_DIR/last_run_config.json"
echo "=== 설정 지문 ==="; echo "$CFG_FINGERPRINT"

echo "=== 씬 ${i} | $(basename "$SCENE_FILE") ==="
echo "  헤드셋: 오른그립=스킬시작/정지 · 왼Y=성공 · 왼X=실패 · 왼그립=저장·종료"
echo "  [record] 이벤트 로그: tail -f $SIM_LOG | grep record"
cd /media/jindong/Data/BLLIC_teleoperate/etri_eai_sim-main
# --camera_include는 teleop.py에서 실제로 안 읽히는 죽은 인자라 삭제함(2026-08-03 확인) — 위 TELEOP_HEADCAM_ONLY가 실제 동작하는 스위치.
# EXTRA_KIT_ARGS: performance/quality.kit 파일을 건드리지 않고 개별 rtx 설정만 실험적으로 오버라이드할 때 사용.
# Kit CLI 인자(--/경로=값)가 .kit 설정파일보다 항상 우선 적용됨. 예)
#   RENDER_MODE=performance EXTRA_KIT_ARGS="--/rtx/raytracing/cached/enabled=true" ./collect_episode.sh 0
[ -n "${EXTRA_KIT_ARGS:-}" ] && echo "  [실험] EXTRA_KIT_ARGS: $EXTRA_KIT_ARGS"
# ── P1-1 코어 핀닝 A/B (2026-08-12) ──────────────────────────────────────────
# PIN_CORES=1 → sim을 물리코어 0-2(+HT 시블링 5,6)에 고정, 코어3(3,7)은 teleop C 전용으로 비움.
# start_teleop_c.sh도 PIN_CORES=1로 띄워야 세트가 완성된다. 미설정 시 기존 동작과 완전 동일.
PIN_PREFIX=""
if [ "${PIN_CORES:-}" = "1" ]; then
  PIN_PREFIX="taskset -c 0-2,5,6"
  echo "  [실험] PIN_CORES=1 → sim CPU 0-2,5,6 고정 (C는 3,7)"
fi
$PIN_PREFIX python teleop.py \
  --scene_name Benevolence_1_int \
  --scene_instance "${i}" \
  --generate_data \
  --generate_data_dir "$DATA_DIR" \
  ${EXTRA_KIT_ARGS:+"--kit_args=$EXTRA_KIT_ARGS"} 2>&1 | tee "$SIM_LOG"

# (Ctrl+C 또는 정상 종료 후) 좀비 정리 + 최근 에피소드 요약
sleep 2; pkill -9 -f "teleop\.py" 2>/dev/null || true
LAST_EP=$(ls -td "$DATA_DIR"/episode_*/ 2>/dev/null | head -1)
if [ -n "$LAST_EP" ] && [ -f "${LAST_EP}skill_annotation.json" ]; then
  echo "=== 저장됨: ${LAST_EP} ==="
  ~/bllic_ws/venv_sim/bin/python -c "import json; d=json.load(open('${LAST_EP}skill_annotation.json')); m=d['episode_meta']; print('  완주:', m['finished'], m['completed_skills'],'/',m['total_skills']); print('  구간:', [(s['skill_idx'],s['attempt'],s['outcome']) for s in d['skill_annotation']])" 2>/dev/null || true
fi

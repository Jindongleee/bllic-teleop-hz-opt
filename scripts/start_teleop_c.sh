#!/bin/bash
# 터미널 C — XR 텔레오프 (물병 세우기 수집용, done-file 연동 포함)
# 그립 버튼: 오른손 그립 첫 누름 = 시작(r 대체), 다시 누름 = 에피소드 종료·저장

# ── 좀비 인스턴스 가드 (2026-08-05 이중발행 사건 재발 방지) ──
# 이전 teleop C가 살아 있으면 두 프로세스가 같은 lowcmd 토픽에 팔 명령을 동시 발행해
# 로봇이 F0↔IK 자세를 오가며 허우적거림. 시작 전 반드시 정리한다 (본인 소유 프로세스만).
if pgrep -u "$USER" -f "teleop_hand_and_arm\.py" >/dev/null; then
  echo "⚠ 이미 실행 중인 teleop_hand_and_arm.py 발견:"
  pgrep -u "$USER" -af "teleop_hand_and_arm\.py"
  read -p "종료하고 계속할까요? [y/N] " _ans
  [ "$_ans" = "y" ] || { echo "중단합니다."; exit 1; }
  pkill -u "$USER" -f "teleop_hand_and_arm\.py"
  sleep 2
  pgrep -u "$USER" -f "teleop_hand_and_arm\.py" >/dev/null && { pkill -9 -u "$USER" -f "teleop_hand_and_arm\.py"; sleep 1; }
  echo "정리 완료. 새 세션을 시작합니다."
fi

source "$HOME/miniforge3/bin/activate" tv
export LD_LIBRARY_PATH="$HOME/bllic_ws/cyclonedds-install/lib"
cd /media/jindong/Data/BLLIC_teleoperate/xr_teleoperate/teleop
export PYTHONUNBUFFERED=1
export MULTI_EPISODE=1              # v2: finish 후 C 유지·다음 에피소드
export IMAGE_SERVER_PORT=5556   # 5555는 타 세션 GR00T 서버와 충돌 가능 → 영구적으로 5556 사용
export STREAM_VR_VIDEO=0        # VR 헤드셋엔 영상 안 띄우고(패스스루 유지) 컨트롤러 트래킹만 사용 — CPU 절약
# ── P1-1 코어 핀닝 A/B (2026-08-12) ──
# PIN_CORES=1 → C 계열 전체(메인+televuer+자식, affinity 상속)를 코어3(3,7)에 고정.
# collect_episode.sh의 PIN_CORES=1과 세트. 미설정 시 기존 동작과 완전 동일.
PIN_PREFIX=""
if [ "${PIN_CORES:-}" = "1" ]; then
  PIN_PREFIX="taskset -c 3,7"
  echo "[실험] PIN_CORES=1 → teleop C를 CPU 3,7에 고정"
fi
$PIN_PREFIX python teleop_hand_and_arm.py \
  --xr-mode=controller --arm=G1_29 --ee=dex1 --sim \
  --done-file "$HOME/bllic_ws/pitcher_task/.episode_done" \
  2>&1 | tee "$HOME/bllic_ws/pitcher_task/data_collect/teleop_c.log"

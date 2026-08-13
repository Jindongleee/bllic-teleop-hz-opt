# BLLIC 텔레옵 수집 Hz 최적화 (14.76 → 22.2Hz)

4코어 Xeon 머신에서 Isaac Sim 기반 텔레옵 데이터 수집 Hz를 **+50%** 끌어올린 기록.
"수집 데이터 양식 불변 + `render_final.py` 호환 유지"를 하드 제약으로 두고 진행.

> ⚠️ **이 레포는 업체(BLLIC) 제공 시뮬레이션 코드(`etri_eai_sim`)를 포함하지 않습니다.**
> 우리가 새로 작성한 파일(`save_worker_proc.py`, `scripts/`), 공개 오픈소스 라이브러리(`vuer`) 패치,
> 그리고 변경 내용을 서술한 문서만 담았습니다. 업체 원본 파일에 손댄 부분은 **env var 이름 +
> 파일/줄 번호 + 로직 설명**으로만 기록했습니다(`HANDOFF_teleop_hz_개선_인수인계.md` 참고).
> 실제 적용은 이 문서를 보면서 각자의 `etri_eai_sim` 사본에 수동으로 반영해야 합니다.

## 최종 결과

**22.2±0.4Hz** (업체 실측 27.7±0.8Hz의 0.80배). 상세 수치·실험 로그는 `HANDOFF_teleop_hz_개선_인수인계.md`.

## 구성

| 경로 | 내용 |
|---|---|
| `HANDOFF_teleop_hz_개선_인수인계.md` | ★메인 문서. 구조·측정법·7가지 개선 사항(문제/원인/수정/주의점/검증법)·기각된 실험·최종 상태 |
| `MANIFEST_원본.md` | 원래 다른 인턴에게 전달했던 적용 절차 원본 (참고용, 경로는 우리 워크스페이스 기준) |
| `action_provider_new_files/save_worker_proc.py` | 신규 작성 파일 (기각된 실험용 자식 프로세스 스크립트, 업체 코드 미기반) |
| `patches/vuer_uplink_busyspin.patch` | 공개 PyPI 패키지 `vuer`(0.0.32RC7) 대상 1줄 패치 — busy-spin 버그 수정 |
| `scripts/` | 우리가 작성한 수집/측정 스크립트 (env var로 업체 스크립트를 호출만 함, 소스 미포함) |

## 적용 안 된 것 (의도적 제외)

업체 원본 파일 5개(`teleop.py`, `action_provider/action_provider_wh_dds.py`, `eval_sim.py`,
`render_final.py`, `tasks/common_config/camera_configs.py`, `tasks/common_observations/camera_state.py`)의
전체 사본·diff는 **업체 코드가 대부분을 차지**하므로 이 레포에 올리지 않았습니다.
필요하면 `HANDOFF_teleop_hz_개선_인수인계.md`를 보고 자기 사본에 직접 반영하세요.

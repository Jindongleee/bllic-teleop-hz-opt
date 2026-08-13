"""P1-2 (2026-08-12): sim_state_raw torch.save 전용 독립 자식 프로세스.

SAVE_WORKER_PROC=1일 때 action_provider_wh_dds.py가 subprocess.Popen으로
이 파일을 **독립 스크립트로** 실행한다 (multiprocessing 아님).

⚠️ multiprocessing(spawn/forkserver)을 쓰지 않는 이유 (2026-08-12 스모크로 확인):
  둘 다 자식 생성 시 부모의 __main__(teleop.py)을 재-import하는데,
  teleop.py는 AppLauncher가 모듈 레벨(:142)이라 자식이 Isaac을 통째로 재기동한다.
  subprocess는 이 파일만 실행하므로 함정이 원천적으로 없다.

프로토콜 (stdin/stdout 바이너리):
  부모 → 자식(stdin) : [8바이트 LE 길이][pickle((filepath, obj))] 반복. 길이 0 = 종료.
  자식 → 부모(stdout): 저장 1건 완료마다 b"1" 1바이트 (부모의 pending 카운터 감소용).

규칙: torch 외 무거운 import 금지, CUDA 초기화 금지(부모가 CUDA_VISIBLE_DEVICES=""로 기동,
넘어오는 텐서는 전부 CPU). 저장 내용·파일명은 스레드 방식과 완전 동일 → 데이터 형식 영향 0.
"""
import pickle
import struct
import sys
import traceback


def _read_exact(stream, n):
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def main():
    import torch

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        hdr = _read_exact(stdin, 8)
        if hdr is None:
            break  # 부모 종료(파이프 닫힘)
        n = struct.unpack("<Q", hdr)[0]
        if n == 0:
            break  # 정상 종료 센티널
        payload = _read_exact(stdin, n)
        if payload is None:
            break
        try:
            filepath, obj = pickle.loads(payload)
            torch.save(obj, filepath)
        except Exception as e:
            print(f"[save-proc] 저장 실패: {e}", file=sys.stderr)
            traceback.print_exc()
        finally:
            stdout.write(b"1")
            stdout.flush()


if __name__ == "__main__":
    main()

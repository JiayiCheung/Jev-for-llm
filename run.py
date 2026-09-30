"""统一入口：python run.py check / serve / doctor / run / compare / summarize。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from jev_vllm.cli import main

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('已中断。')
        raise SystemExit(130)
    except Exception as exc:
        print(f'未完成：{exc}',file=sys.stderr)
        print('连接被拒绝时，请在另一终端运行 serve 并等待启动完成。',file=sys.stderr)
        raise SystemExit(1)

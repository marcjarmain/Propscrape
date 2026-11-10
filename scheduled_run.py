"""Task Scheduler entry point: capture errors and retain a per-run log."""
import datetime, pathlib, subprocess, sys
root=pathlib.Path(__file__).resolve().parent
logs=root/'data'/'logs'; logs.mkdir(parents=True,exist_ok=True)
with (logs/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')).open('w',encoding='utf-8') as f:
    result=subprocess.run([sys.executable,str(root/'market.py'),'--scheduled'],cwd=root,stdout=f,stderr=subprocess.STDOUT)
sys.exit(result.returncode)

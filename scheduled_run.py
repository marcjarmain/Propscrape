"""Task Scheduler entry point: capture errors and retain a per-run log."""
import datetime, pathlib, subprocess, sys, json
root=pathlib.Path(__file__).resolve().parent
logs=root/'data'/'logs'; logs.mkdir(parents=True,exist_ok=True)
state=root/'data'/'last_job.json'
def record(value):
    temp=state.with_suffix('.tmp');temp.write_text(json.dumps(value),encoding='utf-8');temp.replace(state)
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
record({'started':started,'state':'running','exit_code':None})
with (logs/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')).open('w',encoding='utf-8') as f:
    result=subprocess.run([sys.executable,str(root/'market.py'),'--scheduled'],cwd=root,stdout=f,stderr=subprocess.STDOUT)
record({'started':started,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'state':'finished','exit_code':result.returncode})
sys.exit(result.returncode)

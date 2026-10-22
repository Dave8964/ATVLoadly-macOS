"""Exercise a packaged backend with fresh isolated data; never touches live data."""
import json, os, pathlib, socket, subprocess, sys, tempfile, time, urllib.request
app = pathlib.Path(sys.argv[1]).resolve()
bin_dir = app/'Contents/Resources/bin'
results = []
for iteration in range(3):
    with tempfile.TemporaryDirectory(prefix='atvloadly-smoke-') as tmp:
        root = pathlib.Path(tmp); work = root/'data'; work.mkdir()
        (work/'settings.json').write_text(json.dumps({'task':{'enabled':False},'update':{'check_interval':0}}))
        config = root/'config.yaml'
        config.write_text(f'server:\n  listen_addr: 127.0.0.1\n  work_dir: {work}\nlog:\n  log_file: {root}/backend.log\n')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
        env = dict(os.environ, HOME=tmp, PATH=str(bin_dir)+':'+os.environ['PATH'])
        with (root/'stdout.log').open('wb') as log:
            started = time.monotonic()
            p = subprocess.Popen([str(bin_dir/'atvloadly'),'server','-p',str(port),'-c',str(config)],env=env,stdout=log,stderr=log)
            try:
                while time.monotonic()-started < 15:
                    if p.poll() is not None: raise RuntimeError(f'Backend exited {p.returncode}')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/native/ready',timeout=.3) as r:
                            assert json.load(r)['status']=='ready'
                        break
                    except OSError: time.sleep(.05)
                else: raise RuntimeError('Readiness exceeded 15 seconds')
                elapsed = time.monotonic()-started
                for route in ('/','/healthcheck','/api/devices'):
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}'+route,timeout=3) as r: assert r.status==200
                results.append({'run':iteration+1,'seconds_to_ready':round(elapsed,3),'http_routes':'passed'})
            finally:
                p.terminate()
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill();p.wait();raise RuntimeError("Backend did not shut down gracefully")
                if p.returncode != 0: raise RuntimeError(f"Backend shutdown exit status {p.returncode}")
                results[-1]["graceful_shutdown"] = True
print(json.dumps({'kind':'isolated manual process starts, not cold-login tests','results':results},indent=2))

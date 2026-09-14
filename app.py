import os, uuid, json, subprocess, threading, time, shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / 'uploads'
OUTPUTS = BASE / 'outputs'
UPLOADS.mkdir(exist_ok=True); OUTPUTS.mkdir(exist_ok=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024
jobs = {}
lock = threading.Lock()

ALLOWED = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def probe(path):
    cmd = ['ffprobe','-v','error','-print_format','json','-show_format','-show_streams',str(path)]
    p = run(cmd)
    if p.returncode != 0: raise RuntimeError('Could not analyze the video.')
    data = json.loads(p.stdout)
    v = next((s for s in data.get('streams',[]) if s.get('codec_type') == 'video'), {})
    a = next((s for s in data.get('streams',[]) if s.get('codec_type') == 'audio'), {})
    def fps(s):
        x = s.get('avg_frame_rate') or s.get('r_frame_rate') or '0/1'
        try:
            n,d = x.split('/'); return round(float(n)/float(d),2) if float(d) else 0
        except: return 0
    return {
        'duration': float(data.get('format',{}).get('duration') or 0),
        'size': int(data.get('format',{}).get('size') or os.path.getsize(path)),
        'width': int(v.get('width') or 0), 'height': int(v.get('height') or 0),
        'fps': fps(v), 'video_codec': v.get('codec_name','unknown'),
        'audio_codec': a.get('codec_name','none'), 'has_audio': bool(a)
    }

def gpu_available():
    p = run(['ffmpeg','-hide_banner','-encoders'])
    return 'h264_nvenc' in p.stdout

def worker(jid, src, mode):
    try:
        info = probe(src)
        with lock: jobs[jid].update(status='processing', progress=3, info=info, stage='Analyzing source')
        out = OUTPUTS / f'{jid}.mp4'
        duration = max(info['duration'], 0.1)
        # Preserve portrait/landscape dimensions up to 1080p-class output without stretching.
        vf = "scale=w='min(1080,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p"
        # A modest detail pass; MAXIMUM is slightly stronger but still avoids artificial oversharpening.
        if mode == 'maximum':
            vf += ',unsharp=5:5:0.45:5:5:0.15'
            cq = '17'
            preset = 'p5'
        else:
            vf += ',unsharp=5:5:0.28:5:5:0.10'
            cq = '19'
            preset = 'p4'
        encoder = 'h264_nvenc' if gpu_available() else 'libx264'
        cmd = ['ffmpeg','-y','-hide_banner','-i',str(src),'-map','0:v:0','-map','0:a?','-vf',vf,'-c:v',encoder]
        if encoder == 'h264_nvenc':
            cmd += ['-preset',preset,'-tune','hq','-rc','vbr','-cq',cq,'-b:v','0']
        else:
            cmd += ['-preset','medium','-crf',cq]
        cmd += ['-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-progress','pipe:1','-nostats',str(out)]
        with lock: jobs[jid].update(stage='Optimizing frames', encoder=encoder, progress=8)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        while True:
            line = proc.stdout.readline()
            if not line: break
            if line.startswith('out_time_ms='):
                try:
                    sec = int(line.split('=',1)[1]) / 1_000_000
                    pct = min(98, 8 + (sec/duration)*88)
                    with lock: jobs[jid].update(progress=round(pct,1))
                except: pass
        stderr = proc.stderr.read()
        rc = proc.wait()
        if rc != 0: raise RuntimeError(stderr[-1000:] or 'FFmpeg failed.')
        out_info = probe(out)
        with lock: jobs[jid].update(status='done', progress=100, stage='Ready', output=out.name, output_info=out_info)
    except Exception as e:
        with lock: jobs[jid].update(status='error', stage='Failed', error=str(e))
    finally:
        try: src.unlink(missing_ok=True)
        except: pass

def cleanup():
    cutoff = time.time() - 6*3600
    for folder in (UPLOADS, OUTPUTS):
        for p in folder.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime < cutoff: p.unlink()
            except: pass

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/health')
def health():
    return jsonify({'ok':True,'ffmpeg':shutil.which('ffmpeg') is not None,'gpu':gpu_available()})

@app.post('/api/process')
def process():
    cleanup()
    f = request.files.get('video'); mode = request.form.get('mode','stable')
    if not f or not f.filename: return jsonify(error='Choose a video first.'), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED: return jsonify(error='Unsupported video format.'), 400
    jid = uuid.uuid4().hex
    name = secure_filename(f.filename) or f'video{ext}'
    src = UPLOADS / f'{jid}_{name}'
    f.save(src)
    with lock: jobs[jid] = {'status':'queued','progress':0,'stage':'Queued','mode':mode}
    threading.Thread(target=worker,args=(jid,src,mode),daemon=True).start()
    return jsonify(job_id=jid)

@app.get('/api/status/<jid>')
def status(jid):
    with lock: data = dict(jobs.get(jid, {'status':'missing','error':'Job not found.'}))
    return jsonify(data)

@app.get('/download/<name>')
def download(name):
    return send_from_directory(OUTPUTS, name, as_attachment=True, download_name='DONIAWIK_optimized.mp4')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)

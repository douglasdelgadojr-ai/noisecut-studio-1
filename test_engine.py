"""Prueba el motor de exportación (sin abrir la interfaz). Requiere ffmpeg en PATH."""
import re, os, subprocess, tempfile, shutil
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'noisecut.py'), encoding='utf-8').read()
head = re.sub(r'^from PySide6.*$', '', src.split('class Worker')[0], flags=re.M)
ns = {'__name__': 'x'}; exec(head, ns)
Clip, build, probe = ns['Clip'], ns['build'], ns['probe']
d = tempfile.mkdtemp(); os.chdir(d)
def ff(*a): subprocess.run(['ffmpeg', '-v', 'error', '-y', *a], check=True)
ff('-f', 'lavfi', '-i', 'testsrc=d=4:s=1280x720:r=30', '-f', 'lavfi', '-i', 'sine=f=440:d=4',
   '-f', 'lavfi', '-i', 'anoisesrc=d=4:a=0.2', '-filter_complex', '[1][2]amix=inputs=2[a]',
   '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-c:a', 'aac', 'a.mp4')
ff('-f', 'lavfi', '-i', 'color=c=red:s=640x480:d=1', '-frames:v', '1', 'img.png')
ff('-f', 'lavfi', '-i', 'sine=f=300:d=5', 'm.mp3')
dur, au = probe('a.mp4')
clips = [Clip('a.mp4', 'video', dur, au, 0, 2, speed=1.5, bright=0.1, blur=2, denoise=15, fade=0.3),
         Clip('img.png', 'image', 5, False, 0, 2), Clip('a.mp4', 'video', dur, au, 2, 4)]
texts = [dict(text='Hola: mundo', start=0, end=3, x=50, y=85, size=64, color='#ffffff')]
stick = [dict(path='img.png', start=0, end=2, x=85, y=15, w=20)]
music = [dict(path='m.mp3', offset=1, vol=0.5, denoise=10)]
cmd, T = build(clips, texts, stick, music, 'out.mp4', d)
cmd = [x for x in cmd if x not in ('-progress', 'pipe:1')]
r = subprocess.run(cmd, capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-1500:]
assert os.path.getsize('out.mp4') > 1000
print('OK: exportación correcta, duración esperada %.2fs' % T)
shutil.rmtree(d, ignore_errors=True)

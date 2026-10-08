#!/usr/bin/env python3
"""NoiseCut Studio: editor de video de escritorio con reducción de ruido de fondo.
PySide6 (interfaz) + FFmpeg (procesamiento y exportación)."""
import sys, os, json, shutil, subprocess, tempfile, copy
from dataclasses import dataclass
from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QColor, QAction, QIcon
from PySide6.QtWidgets import *
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

W, H, FPS = 1920, 1080, 30
VID = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
IMG = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
AUD = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}
NOWIN = 0x08000000 if os.name == 'nt' else 0


def resource_path(*parts):
    root = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def ffbin(name):
    here = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'ffmpeg', name)
    for p in (here, here + '.exe'):
        if os.path.exists(p):
            return p
    return shutil.which(name)


def probe(path):
    r = subprocess.run([ffbin('ffprobe'), '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
                        '-of', 'json', path], capture_output=True, text=True, creationflags=NOWIN)
    j = json.loads(r.stdout or '{}')
    dur = float(j.get('format', {}).get('duration') or 0)
    return dur, any(s.get('codec_type') == 'audio' for s in j.get('streams', []))


@dataclass
class Clip:
    path: str
    kind: str
    src: float
    audio: bool
    start: float = 0.0
    end: float = 0.0
    speed: float = 1.0
    bright: float = 0.0
    contrast: float = 1.0
    sat: float = 1.0
    blur: float = 0.0
    denoise: int = 0
    fade: float = 0.0

    @property
    def out(self):
        return max(0.1, (self.end - self.start) / self.speed)


def esc(p):
    return p.replace('\\', '/').replace(':', '\\:').replace("'", "\\'")


def sysfont():
    for p in ('C:/Windows/Fonts/arial.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if os.path.exists(p):
            return p


def atempo(s):
    f = []
    while s > 2:
        f.append('atempo=2'); s /= 2
    while s < 0.5:
        f.append('atempo=0.5'); s *= 2
    f.append(f'atempo={s:.4f}')
    return f


def denoise_f(nr):
    # Reducción espectral (FFmpeg afftdn) + filtro de graves (retumbos, ventiladores)
    return f'highpass=f=80,afftdn=nr={nr}:nf=-30:tn=1' if nr > 0 else None


def build(clips, texts, stickers, music, out, tmp, size=(W, H)):
    width, height = size
    a = [ffbin('ffmpeg'), '-y', '-hide_banner', '-nostats', '-progress', 'pipe:1']
    fc, n = [], 0
    for i, c in enumerate(clips):
        if c.kind == 'image':
            a += ['-loop', '1', '-framerate', str(FPS), '-t', f'{c.out:.3f}', '-i', c.path]
        else:
            a += ['-i', c.path]
        n += 1
        v = [] if c.kind == 'image' else [f'trim=start={c.start}:end={c.end}']
        v += [f'setpts=(PTS-STARTPTS)/{c.speed}', f'scale={width}:{height}:force_original_aspect_ratio=decrease',
              f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2', 'setsar=1', f'fps={FPS}',
              f'eq=brightness={c.bright}:contrast={c.contrast}:saturation={c.sat}']
        if c.blur > 0:
            v.append(f'gblur=sigma={c.blur}')
        fo = max(0, c.out - c.fade)
        if c.fade > 0:
            v += [f'fade=t=in:st=0:d={c.fade}', f'fade=t=out:st={fo:.3f}:d={c.fade}']
        fc.append(f'[{i}:v]{",".join(v)}[v{i}]')
        if c.kind == 'video' and c.audio:
            f = [f'atrim=start={c.start}:end={c.end}', 'asetpts=PTS-STARTPTS'] + atempo(c.speed)
            d = denoise_f(c.denoise)
            if d:
                f.append(d)
            if c.fade > 0:
                f += [f'afade=t=in:st=0:d={c.fade}', f'afade=t=out:st={fo:.3f}:d={c.fade}']
            f.append('aformat=sample_rates=48000:channel_layouts=stereo')
            fc.append(f'[{i}:a]{",".join(f)}[a{i}]')
        else:
            fc.append(f'anullsrc=r=48000:cl=stereo,atrim=0:{c.out:.3f},asetpts=PTS-STARTPTS[a{i}]')
    cat = ''.join(f'[v{i}][a{i}]' for i in range(len(clips)))
    fc.append(f'{cat}concat=n={len(clips)}:v=1:a=1[vc][ac]')
    T = sum(c.out for c in clips)
    cur, font = 'vc', sysfont()
    for t in texts:
        k = len(fc)
        fp = os.path.join(tmp, f't{k}.txt')
        with open(fp, 'w', encoding='utf-8') as fh:
            fh.write(t['text'])
        ff = f":fontfile='{esc(font)}'" if font else ''
        s0, e0 = t['start'], t['end']
        fc.append(f"[{cur}]drawtext=textfile='{esc(fp)}'{ff}:fontsize={t['size']}:fontcolor={t['color']}"
                  f":borderw=2:bordercolor=black@0.6:x=(w-text_w)*{t['x']}/100:y=(h-text_h)*{t['y']}/100"
                  f":alpha='if(lt(t,{s0}),0,min(1,(t-{s0})/0.4))':enable='between(t,{s0},{e0})'[x{k}]")
        cur = f'x{k}'
    for s in stickers:
        a += ['-loop', '1', '-framerate', str(FPS), '-t', f'{T:.3f}', '-i', s['path']]
        j, k = n, len(fc)
        n += 1
        fc.append(f"[{j}:v]scale={int(width * s['w'] / 100)}:-1,format=rgba[s{k}]")
        fc.append(f"[{cur}][s{k}]overlay=x=(main_w-overlay_w)*{s['x']}/100:y=(main_h-overlay_h)*{s['y']}/100"
                  f":enable='between(t,{s['start']},{s['end']})'[y{k}]")
        cur = f'y{k}'
    labels = ['ac']
    for m in music:
        a += ['-i', m['path']]
        j = n
        n += 1
        f = []
        d = denoise_f(m['denoise'])
        if d:
            f.append(d)
        ms = int(m['offset'] * 1000)
        f += [f"volume={m['vol']}", f'adelay={ms}|{ms}', 'aformat=sample_rates=48000:channel_layouts=stereo']
        fc.append(f'[{j}:a]{",".join(f)}[m{j}]')
        labels.append(f'm{j}')
    if len(labels) > 1:
        fc.append(''.join(f'[{l}]' for l in labels) +
                  f'amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[aout]')
    else:
        fc.append('[ac]anull[aout]')
    a += ['-filter_complex', ';'.join(fc), '-map', f'[{cur}]', '-map', '[aout]', '-c:v', 'libx264',
          '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
          '-movflags', '+faststart', out]
    return a, T


class Worker(QThread):
    prog = Signal(int)
    done = Signal(str)

    def __init__(s, cmd, total):
        super().__init__()
        s.cmd, s.total = cmd, max(total, 0.1)

    def run(s):
        p = subprocess.Popen(s.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding='utf-8', errors='replace', creationflags=NOWIN)
        tail = []
        for line in p.stdout:
            if line.startswith('out_time_us='):
                try:
                    s.prog.emit(min(99, int(int(line.split('=')[1]) / 1e6 / s.total * 100)))
                except ValueError:
                    pass
            else:
                tail = (tail + [line])[-15:]
        p.wait()
        s.done.emit('' if p.returncode == 0 else ''.join(tail))


def pick(b):
    c = QColorDialog.getColor(QColor(b.text()))
    if c.isValid():
        b.setText(c.name()); b.setStyleSheet(f'background:{c.name()};color:#888')


def ask(parent, title, spec, vals=None):
    d = QDialog(parent); d.setWindowTitle(title)
    f, w, vals = QFormLayout(d), {}, vals or {}
    for key, label, typ, dflt, *rng in spec:
        v = vals.get(key, dflt)
        if typ == 'text':
            e = QLineEdit(str(v))
        elif typ == 'color':
            e = QPushButton(v); e.setStyleSheet(f'background:{v};color:#888')
            e.clicked.connect(lambda _=0, b=e: pick(b))
        else:
            e = QDoubleSpinBox(); e.setRange(*rng); e.setDecimals(2 if typ == 'float' else 0); e.setValue(v)
        w[key] = (typ, e); f.addRow(label, e)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); f.addRow(bb)
    if not d.exec():
        return None
    out = {}
    for k, (typ, e) in w.items():
        out[k] = e.text() if typ in ('text', 'color') else (int(e.value()) if typ == 'int' else e.value())
    return out


TEXT = [('text', 'Texto', 'text', 'Hola'), ('start', 'Inicio (s)', 'float', 0, 0, 3600),
        ('end', 'Fin (s)', 'float', 5, 0, 3600), ('x', 'Posición X %', 'int', 50, 0, 100),
        ('y', 'Posición Y %', 'int', 85, 0, 100), ('size', 'Tamaño', 'int', 64, 8, 400),
        ('color', 'Color', 'color', '#ffffff')]
STICK = [('start', 'Inicio (s)', 'float', 0, 0, 3600), ('end', 'Fin (s)', 'float', 5, 0, 3600),
         ('x', 'Posición X %', 'int', 85, 0, 100), ('y', 'Posición Y %', 'int', 15, 0, 100),
         ('w', 'Ancho (% del video)', 'int', 20, 1, 100)]
MUSIC = [('offset', 'Empieza en (s)', 'float', 0, 0, 3600), ('vol', 'Volumen', 'float', 1.0, 0, 4),
         ('denoise', 'Reducir ruido (dB, 0 = off)', 'int', 0, 0, 40)]
FIELDS = [('start', 'Inicio (s)', 0, 36000, 0.1, 2), ('end', 'Fin / duración (s)', 0.1, 36000, 0.1, 2),
          ('speed', 'Velocidad ×', 0.25, 4, 0.05, 2), ('bright', 'Brillo', -1, 1, 0.05, 2),
          ('contrast', 'Contraste', 0, 3, 0.05, 2), ('sat', 'Saturación', 0, 3, 0.05, 2),
          ('blur', 'Desenfoque', 0, 30, 0.5, 1), ('fade', 'Transición: fundido (s)', 0, 3, 0.1, 1)]
STYLE = """QWidget{background:#1e1f24;color:#e6e6e6;font-size:13px}
QListWidget,QLineEdit,QDoubleSpinBox{background:#2a2c33;border:1px solid #3a3d46;border-radius:4px;padding:3px}
QPushButton{background:#3b82f6;border:none;border-radius:5px;padding:7px 12px;color:white}
QPushButton:hover{background:#2f6fe0}QListWidget::item:selected{background:#3b82f6}
QGroupBox{border:1px solid #3a3d46;border-radius:6px;margin-top:10px;padding-top:8px}
QGroupBox::title{subcontrol-origin:margin;left:8px}QTabBar::tab{padding:6px 12px;background:#2a2c33}
QTabBar::tab:selected{background:#3b82f6}"""


class Main(QMainWindow):
    def __init__(s):
        super().__init__()
        s.setWindowTitle('NoiseCut Studio'); s.resize(1400, 860)
        icon = resource_path('assets', 'icon.png')
        if os.path.exists(icon):
            s.setWindowIcon(QIcon(icon))
        s.texts, s.stickers, s.music, s.cur = [], [], [], None
        s.track_refresh = []
        s.project_path = None
        s.history, s.history_index = [], -1
        s.player, s.aout, s.video = QMediaPlayer(), QAudioOutput(), QVideoWidget()
        s.player.setAudioOutput(s.aout); s.player.setVideoOutput(s.video)
        # --- panel izquierdo: medios
        left = QWidget(); ll = QVBoxLayout(left)
        imp = QPushButton('＋ Importar video / audio / imagen'); imp.clicked.connect(s.import_media)
        s.bin = QListWidget(); s.bin.itemDoubleClicked.connect(s.add_to_timeline)
        ll.addWidget(imp); ll.addWidget(QLabel('Doble clic para añadir a la línea de tiempo')); ll.addWidget(s.bin)
        # --- centro: vista previa + pistas
        mid = QWidget(); ml = QVBoxLayout(mid)
        s.video.setMinimumHeight(300); ml.addWidget(s.video, 3)
        ctl = QHBoxLayout(); s.play = QPushButton('▶ / ⏸'); s.play.clicked.connect(s.toggle)
        s.preview_effects = QPushButton('Vista previa con efectos'); s.preview_effects.clicked.connect(s.render_preview)
        s.seek = QSlider(Qt.Horizontal); s.seek.sliderMoved.connect(s.player.setPosition)
        s.player.positionChanged.connect(s.on_pos); s.player.durationChanged.connect(lambda d: s.seek.setRange(0, d))
        ctl.addWidget(s.play); ctl.addWidget(s.seek); ctl.addWidget(s.preview_effects); ml.addLayout(ctl)
        tabs = QTabWidget(); ml.addWidget(tabs, 2)
        tw = QWidget(); tl = QVBoxLayout(tw)
        s.tl = QListWidget(); s.tl.setDragDropMode(QAbstractItemView.InternalMove)
        s.tl.model().rowsAboutToBeMoved.connect(lambda *_: s.remember())
        s.tl.model().rowsMoved.connect(s.renumber); s.tl.currentItemChanged.connect(s.select)
        row = QHBoxLayout()
        for label, fn in (('✂ Dividir en el cabezal', s.split), ('⧉ Duplicar', s.dup), ('🗑 Eliminar', s.rm)):
            b = QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        tl.addWidget(s.tl); tl.addLayout(row)
        tabs.addTab(tw, '🎞 Línea de tiempo (arrastra para ordenar)')
        tabs.addTab(s.track(s.texts, TEXT, 'Texto', lambda x: f"“{x['text']}”  {x['start']}–{x['end']}s"), 'Texto')
        tabs.addTab(s.track(s.stickers, STICK, 'Sticker', lambda x: f"{os.path.basename(x['path'])}  {x['start']}–{x['end']}s",
                            'Imágenes (*.png *.webp *.jpg *.jpeg)'), 'Stickers')
        tabs.addTab(s.track(s.music, MUSIC, 'Audio', lambda x: f"{os.path.basename(x['path'])}  vol {x['vol']}  ruido {x['denoise']}dB",
                            'Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)'), 'Música / Audio')
        # --- derecha: inspector
        right = QWidget(); rl = QVBoxLayout(right)
        g = QGroupBox('Ajustes del clip'); f = QFormLayout(g); s.sp = {}
        for k, lab, lo, hi, st, dec in FIELDS:
            sp = QDoubleSpinBox(); sp.setRange(lo, hi); sp.setSingleStep(st); sp.setDecimals(dec)
            sp.valueChanged.connect(lambda v, k=k: s.setf(k, v)); s.sp[k] = sp; f.addRow(lab, sp)
        g2 = QGroupBox('🔇 Reducción de ruido de fondo'); f2 = QFormLayout(g2)
        nz = QSpinBox(); nz.setRange(0, 40); nz.valueChanged.connect(lambda v: s.setf('denoise', v)); s.sp['denoise'] = nz
        f2.addRow('Intensidad (dB, 0 = off)', nz)
        f2.addRow(QLabel('Voz con ruido/ventilador: prueba 12–20 dB.\nMás de 25 dB puede sonar metálico.'))
        ex = QPushButton('⬇ Exportar video (MP4)'); ex.clicked.connect(s.export)
        rl.addWidget(g); rl.addWidget(g2); rl.addStretch(); rl.addWidget(ex)
        sp = QSplitter(); sp.addWidget(left); sp.addWidget(mid); sp.addWidget(right)
        sp.setSizes([260, 800, 340]); s.setCentralWidget(sp)
        menu = s.menuBar().addMenu('Proyecto')
        for label, fn, shortcut in (('Nuevo proyecto', s.new_project, 'Ctrl+N'),
                                    ('Abrir proyecto…', s.open_project, 'Ctrl+O'),
                                    ('Guardar proyecto', s.save_project, 'Ctrl+S'),
                                    ('Guardar proyecto como…', s.save_project_as, 'Ctrl+Shift+S')):
            act = QAction(label, s); act.setShortcut(shortcut); act.triggered.connect(fn); menu.addAction(act)
        edit = s.menuBar().addMenu('Editar')
        for label, fn, shortcut in (('Deshacer', s.undo, 'Ctrl+Z'), ('Rehacer', s.redo, 'Ctrl+Y')):
            act = QAction(label, s); act.setShortcut(shortcut); act.triggered.connect(fn); edit.addAction(act)
        s.remember()
        if not ffbin('ffmpeg') or not ffbin('ffprobe'):
            QMessageBox.warning(s, 'Falta FFmpeg', 'No se encuentran FFmpeg y FFprobe. Instala FFmpeg (Windows: winget install ffmpeg) y reinicia la app.')

    def track(s, items, spec, label, fmt, filt=None):
        w = QWidget(); l = QVBoxLayout(w); lst = QListWidget(); l.addWidget(lst); row = QHBoxLayout()

        def redraw():
            lst.clear(); lst.addItems([fmt(x) for x in items])

        def new(path=None):
            base = {}
            if filt:
                path = path or QFileDialog.getOpenFileName(s, label, '', filt)[0]
                if not path:
                    return
                base['path'] = path
            r = ask(s, label, spec)
            if r is not None:
                s.remember(); r.update(base); items.append(r); redraw()

        def edit(it):
            i = lst.row(it); r = ask(s, label, spec, items[i])
            if r is not None:
                s.remember(); items[i].update(r); redraw()

        def delete():
            if lst.currentRow() >= 0:
                s.remember(); items.pop(lst.currentRow()); redraw()
        add, rmb = QPushButton('＋ Añadir'), QPushButton('Eliminar')
        add.clicked.connect(lambda: new()); rmb.clicked.connect(delete); lst.itemDoubleClicked.connect(edit)
        row.addWidget(add); row.addWidget(rmb); l.addLayout(row)
        s.track_refresh.append(redraw)
        w.add_path = new
        if filt and label == 'Audio':
            s.add_music = new
        return w

    def import_media(s):
        ps, _ = QFileDialog.getOpenFileNames(s, 'Importar', '', 'Medios (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.png *.jpg *.jpeg *.bmp *.webp *.mp3 *.wav *.m4a *.aac *.flac *.ogg)')
        for p in ps:
            it = QListWidgetItem(os.path.basename(p)); it.setData(Qt.UserRole, p); s.bin.addItem(it)

    def add_to_timeline(s, it):
        p = it.data(Qt.UserRole); ext = os.path.splitext(p)[1].lower()
        if ext in AUD:
            return s.add_music(p)
        if ext in IMG:
            c = Clip(p, 'image', 5, False, 0, 5)
        else:
            try:
                dur, has_audio = probe(p)
            except (OSError, ValueError, json.JSONDecodeError):
                return QMessageBox.critical(s, 'No se pudo abrir el medio',
                    'No se pudo leer este archivo. Comprueba que FFprobe esté instalado y que el video sea compatible.')
            if dur <= 0:
                return QMessageBox.critical(s, 'Video no compatible', 'El archivo no tiene una duración válida o está dañado.')
            c = Clip(p, 'video', dur, has_audio, 0, dur)
        s.push(c)

    def push(s, c, row=None):
        s.remember()
        it = QListWidgetItem(); it.setData(Qt.UserRole, c)
        s.tl.insertItem(s.tl.count() if row is None else row, it); s.renumber(); s.tl.setCurrentItem(it)

    def renumber(s, *_):
        for i in range(s.tl.count()):
            it = s.tl.item(i); c = it.data(Qt.UserRole)
            it.setText(f"{i + 1}. {os.path.basename(c.path)} · {c.out:.1f}s{'  🔇' if c.denoise else ''}")

    def select(s, it, _=None):
        s.cur = it.data(Qt.UserRole) if it else None
        if not s.cur:
            return
        for k, w in s.sp.items():
            w.blockSignals(True); w.setValue(getattr(s.cur, k)); w.blockSignals(False)
        v = s.cur.kind == 'video'
        s.sp['start'].setEnabled(v); s.sp['speed'].setEnabled(v); s.sp['denoise'].setEnabled(v)
        if v:
            s.player.setSource(QUrl.fromLocalFile(s.cur.path)); s.player.setPosition(int(s.cur.start * 1000)); s.player.pause()

    def setf(s, k, v):
        if s.cur:
            if getattr(s.cur, k) == (int(v) if k == 'denoise' else v):
                return
            s.remember()
            setattr(s.cur, k, int(v) if k == 'denoise' else v); s.renumber()

    def toggle(s):
        s.player.pause() if s.player.playbackState() == QMediaPlayer.PlayingState else s.player.play()

    def on_pos(s, p):
        s.seek.setValue(p)
        if s.cur and s.cur.kind == 'video' and p / 1000 >= s.cur.end:
            s.player.pause()

    def render_preview(s):
        it = s.tl.currentItem()
        if not it:
            return QMessageBox.information(s, 'Vista previa', 'Selecciona un clip de la línea de tiempo.')
        if not ffbin('ffmpeg'):
            return QMessageBox.critical(s, 'Falta FFmpeg', 'Instala FFmpeg y vuelve a abrir NoiseCut Studio.')
        c = copy.deepcopy(it.data(Qt.UserRole))
        if c.kind == 'video' and s.player.source().toLocalFile() == c.path:
            c.start = max(c.start, min(c.end - 0.1, s.player.position() / 1000))
        c.end = min(c.end, c.start + 8 * c.speed)
        s.preview_dir = tempfile.mkdtemp(prefix='noisecut_preview_')
        preview_file = os.path.join(s.preview_dir, 'preview.mp4')
        try:
            cmd, duration = build([c], [], [], [], preview_file, s.preview_dir, size=(640, 360))
        except (OSError, ValueError) as e:
            shutil.rmtree(s.preview_dir, ignore_errors=True)
            return QMessageBox.critical(s, 'Vista previa', f'No se pudo preparar la vista previa.\n{e}')
        s.preview_effects.setEnabled(False); s.statusBar().showMessage('Generando vista previa con efectos…')
        s.preview_worker = Worker(cmd, duration)
        s.preview_worker.done.connect(lambda err: s.preview_finished(err, preview_file))
        s.preview_worker.start()

    def preview_finished(s, err, path):
        s.preview_effects.setEnabled(True)
        if err:
            s.statusBar().clearMessage()
            QMessageBox.critical(s, 'Vista previa', 'No se pudo generar la vista previa. Comprueba que FFmpeg tenga los códecs necesarios.')
            return
        s.player.setSource(QUrl.fromLocalFile(path)); s.player.play()
        s.statusBar().showMessage('Vista previa de hasta 8 segundos con los efectos del clip.')

    def split(s):
        it = s.tl.currentItem()
        if not it:
            return
        c, t = it.data(Qt.UserRole), s.player.position() / 1000
        if c.kind != 'video' or not (c.start + 0.1 < t < c.end - 0.1):
            return QMessageBox.information(s, 'Dividir', 'Mueve el cabezal (barra de reproducción) dentro del clip.')
        s.remember()
        n = copy.copy(c); n.start = t; c.end = t
        s.push(n, s.tl.row(it) + 1)

    def dup(s):
        it = s.tl.currentItem()
        if it:
            s.remember()
            s.push(copy.copy(it.data(Qt.UserRole)), s.tl.row(it) + 1)

    def rm(s):
        r = s.tl.currentRow()
        if r >= 0:
            s.remember()
            s.tl.takeItem(r); s.cur = None; s.renumber()

    def state(s):
        return {'clips': [copy.deepcopy(s.tl.item(i).data(Qt.UserRole)) for i in range(s.tl.count())],
                'texts': copy.deepcopy(s.texts), 'stickers': copy.deepcopy(s.stickers),
                'music': copy.deepcopy(s.music)}

    def remember(s):
        if not hasattr(s, 'tl'):
            return
        current = s.state()
        if s.history_index >= 0 and current == s.history[s.history_index]:
            return
        s.history = s.history[:s.history_index + 1]
        s.history.append(current); s.history_index = len(s.history) - 1

    def restore(s, state):
        s.tl.clear()
        for c in copy.deepcopy(state['clips']):
            it = QListWidgetItem(); it.setData(Qt.UserRole, c); s.tl.addItem(it)
        s.texts[:] = copy.deepcopy(state['texts'])
        s.stickers[:] = copy.deepcopy(state['stickers'])
        s.music[:] = copy.deepcopy(state['music'])
        for refresh in s.track_refresh:
            refresh()
        s.cur = None; s.renumber()

    def undo(s):
        s.remember()
        if s.history_index > 0:
            s.history_index -= 1; s.restore(s.history[s.history_index])

    def redo(s):
        if s.history_index + 1 < len(s.history):
            s.history_index += 1; s.restore(s.history[s.history_index])

    def project_data(s):
        state = s.state()
        return {'format': 'NoiseCutStudio', 'version': 1,
                'clips': [vars(c) for c in state['clips']], 'texts': state['texts'],
                'stickers': state['stickers'], 'music': state['music']}

    def save_project_as(s):
        path, _ = QFileDialog.getSaveFileName(s, 'Guardar proyecto', 'mi_proyecto.ncs', 'Proyecto NoiseCut (*.ncs *.json)')
        if path:
            s.project_path = path; s.save_project()

    def save_project(s):
        if not s.project_path:
            return s.save_project_as()
        try:
            with open(s.project_path, 'w', encoding='utf-8') as f:
                json.dump(s.project_data(), f, ensure_ascii=False, indent=2)
            s.statusBar().showMessage(f'Proyecto guardado: {s.project_path}', 5000)
        except (OSError, TypeError) as e:
            QMessageBox.critical(s, 'No se pudo guardar', f'No se pudo guardar el proyecto.\n{e}')

    def open_project(s):
        path, _ = QFileDialog.getOpenFileName(s, 'Abrir proyecto', '', 'Proyecto NoiseCut (*.ncs *.json)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if data.get('format') != 'NoiseCutStudio' or data.get('version') != 1:
                raise ValueError('El archivo no es un proyecto compatible de NoiseCut Studio.')
            state = {'clips': [Clip(**c) for c in data.get('clips', [])],
                     'texts': data.get('texts', []), 'stickers': data.get('stickers', []),
                     'music': data.get('music', [])}
            paths = [c.path for c in state['clips']] + [x['path'] for x in state['stickers']] + [x['path'] for x in state['music']]
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                raise ValueError('No se encuentran estos archivos de medios:\n' + '\n'.join(missing[:8]))
            s.restore(state); s.project_path = path; s.history = []; s.history_index = -1; s.remember()
            QMessageBox.information(s, 'Proyecto abierto', 'Proyecto cargado correctamente. Los medios conservan sus rutas originales.')
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
            QMessageBox.critical(s, 'No se pudo abrir', str(e))

    def new_project(s):
        s.restore({'clips': [], 'texts': [], 'stickers': [], 'music': []})
        s.project_path = None; s.history = []; s.history_index = -1; s.remember()

    def export(s):
        clips = [s.tl.item(i).data(Qt.UserRole) for i in range(s.tl.count())]
        if not clips:
            return QMessageBox.information(s, 'Exportar', 'Añade al menos un clip a la línea de tiempo.')
        if not ffbin('ffmpeg') or not ffbin('ffprobe'):
            return QMessageBox.critical(s, 'Falta FFmpeg', 'No se encuentran FFmpeg y FFprobe. Instálalos y vuelve a abrir NoiseCut Studio.')
        out, _ = QFileDialog.getSaveFileName(s, 'Exportar', 'mi_video.mp4', 'Video MP4 (*.mp4)')
        if not out:
            return
        tmp = tempfile.mkdtemp()
        try:
            cmd, T = build(clips, s.texts, s.stickers, s.music, out, tmp)
        except (OSError, ValueError, KeyError, TypeError) as e:
            shutil.rmtree(tmp, ignore_errors=True)
            return QMessageBox.critical(s, 'No se pudo preparar la exportación', f'Revisa los ajustes y los archivos de medios.\n{e}')
        s.dlg = QProgressDialog('Exportando…', None, 0, 100, s); s.dlg.setWindowModality(Qt.WindowModal); s.dlg.show()
        s.wk = Worker(cmd, T); s.wk.prog.connect(s.dlg.setValue)
        s.wk.done.connect(lambda err: s.finished(err, out, tmp)); s.wk.start()

    def finished(s, err, out, tmp):
        s.dlg.close(); shutil.rmtree(tmp, ignore_errors=True)
        if err:
            QMessageBox.critical(s, 'Error al exportar', err)
        else:
            QMessageBox.information(s, 'Listo', f'Video exportado:\n{out}')


if __name__ == '__main__':
    app = QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    w = Main(); w.show(); sys.exit(app.exec())

#!/usr/bin/env python3
"""Build a local character-only sample from a generated sequence manifest."""
import argparse
import base64
import html
import json
import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'assets/player'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--embed', action='store_true', help='Also create self-contained preview.html.')
    parser.add_argument('--title', default='人物关键帧动画')
    parser.add_argument('--label', default='人物随鼠标改变姿态，左右方向键切换姿态，Home键回到中性姿态')
    args = parser.parse_args()
    source = args.manifest.resolve()
    data = json.loads(source.read_text(encoding='utf-8'))
    positions = data['positions']; frames = data['frames']; front = data['frontFrame']
    if len(positions) != len(frames) or len(frames) < 2 or not 0 <= front < len(frames):
        raise SystemExit('Invalid frame count or neutral frame in manifest.')
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in positions) or any(b <= a for a, b in zip(positions, positions[1:])):
        raise SystemExit('Frame positions are not strictly increasing.')
    if data.get('previewOnly'):
        print('Note: this is the sparse inspection sequence, not a finished smooth animation.')
    frame_size = data['frameSize']
    if isinstance(frame_size, int): frame_size = [frame_size, frame_size]
    css = (ASSETS/'character-player.css').read_text(encoding='utf-8')
    js = (ASSETS/'character-player.js').read_text(encoding='utf-8')
    meta = json.dumps({'positions': positions, 'frontFrame': front}, ensure_ascii=False).replace('<', r'\u003c')

    def asset_url(relative, embed):
        relative = Path(relative)
        path = (source.parent/relative).resolve()
        if not path.is_relative_to(source.parent) or not path.is_file():
            raise SystemExit('Asset paths must refer to existing files inside the sequence folder.')
        if not embed: return relative.as_posix()
        mime = 'image/png' if path.suffix.lower() == '.png' else 'image/webp'
        return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()

    def document(embed):
        poster_url = asset_url(data.get('poster', frames[front]['src']), embed)
        images = [f'<img data-character-poster src="{html.escape(poster_url, quote=True)}" width="{frame_size[0]}" height="{frame_size[1]}" alt="">']
        for index, frame in enumerate(frames):
            url = asset_url(frame['src'], embed)
            neutral = ' data-character-neutral hidden' if index == front else ' hidden'
            images.append(f'<img data-character-frame="{index}" src="{html.escape(url, quote=True)}" width="{frame_size[0]}" height="{frame_size[1]}" alt="" decoding="async"{neutral}>')
        styles = f'<style>{css}</style>' if embed else '<link rel="stylesheet" href="character-player.css">'
        scripts = f'<script>{js}</script>' if embed else '<script src="character-player.js" defer></script>'
        return f'''<!doctype html><!-- character-keyframe-player --><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(args.title)}</title>{styles}<style>*{{box-sizing:border-box}}body{{margin:0;background:#f2ece1;color:#473a2e;font:16px system-ui}}main{{min-height:100svh;display:grid;align-content:center;padding:28px 24px;gap:16px}}h1{{font-size:22px;margin:0;text-align:center}}[data-keyframe-character]{{--character-ratio:{frame_size[0]/frame_size[1]:.8f};--character-max-size:{min(680,frame_size[0])}px}}</style>{scripts}</head><body><main data-character-scene><h1>{html.escape(args.title)}</h1><div data-keyframe-character><div data-character-control role="img" tabindex="0" aria-label="{html.escape(args.label, quote=True)}"><div data-character-frames>{''.join(images)}</div></div><script type="application/json" data-character-sequence>{meta}</script></div></main></body></html>'''
    # This generator owns only its dedicated sample pages, never an existing site.
    targets = ['index.html'] + (['preview.html'] if args.embed else [])
    for filename in targets:
        path = source.parent/filename
        if path.exists() and '<!-- character-keyframe-player -->' not in path.read_text(encoding='utf-8'):
            raise SystemExit(f'Refusing to overwrite an unrelated page: {path}. Use a dedicated animation output folder.')
    # Validate paths and compose before replacing any file.
    normal = document(False)
    embedded = document(True) if args.embed else None
    (source.parent/'character-player.css').write_text(css, encoding='utf-8')
    (source.parent/'character-player.js').write_text(js, encoding='utf-8')
    (source.parent/'index.html').write_text(normal, encoding='utf-8')
    if embedded: (source.parent/'preview.html').write_text(embedded, encoding='utf-8')
    print(source.parent/('preview.html' if args.embed else 'index.html'))

if __name__ == '__main__': main()

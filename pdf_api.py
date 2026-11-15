import os, subprocess, uuid, shutil, urllib.request, hashlib, time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
WORK_DIR = '/tmp/pdf_api'
SERVE_DIR = '/tmp/pdf_serve'
CACHE_DIR = '/tmp/pdf_cache'
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(SERVE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

pdf_cache = {}
CACHE_TTL = 1800

def get_cached_pdf(url):
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    if url_hash in pdf_cache:
        entry = pdf_cache[url_hash]
        if time.time() - entry['timestamp'] < CACHE_TTL:
            if os.path.exists(entry['path']):
                return entry['path']
    pdf_path = os.path.join(CACHE_DIR, f'{url_hash}.pdf')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(pdf_path, 'wb') as f:
            shutil.copyfileobj(resp, f)
    pdf_cache[url_hash] = {'path': pdf_path, 'timestamp': time.time()}
    return pdf_path

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/v1/pdf/info', methods=['POST'])
def pdf_info():
    data = request.get_json(force=True)
    pdf_url = data.get('url', '')
    if not pdf_url:
        return jsonify({'error': True, 'message': 'Missing url'}), 400
    try:
        pdf_path = get_cached_pdf(pdf_url)
    except Exception as e:
        return jsonify({'error': True, 'message': f'Download failed: {e}'}), 400
    try:
        result = subprocess.run(['pdfinfo', pdf_path], capture_output=True, text=True, timeout=30)
        page_count = 0
        for line in result.stdout.split('\n'):
            if line.strip().startswith('Pages:'):
                page_count = int(line.split(':')[1].strip())
                break
        return jsonify({'error': False, 'status': 200, 'info': {'PageCount': page_count}, 'credits': 0, 'remainingCredits': 999999})
    except Exception as e:
        return jsonify({'error': True, 'message': str(e)}), 500

@app.route('/v1/pdf/convert/to/png', methods=['POST'])
def convert_to_png():
    data = request.get_json(force=True)
    pdf_url = data.get('url', '')
    pages = data.get('pages', '')
    resolution = int(data.get('resolution', 150))
    if not pdf_url:
        return jsonify({'error': True, 'message': 'Missing url'}), 400
    job_id = str(uuid.uuid4())[:8]
    output_prefix = os.path.join(WORK_DIR, job_id)
    serve_dir = os.path.join(SERVE_DIR, job_id)
    os.makedirs(serve_dir, exist_ok=True)
    try:
        pdf_path = get_cached_pdf(pdf_url)
    except Exception as e:
        return jsonify({'error': True, 'message': f'Download failed: {e}'}), 400
    try:
        cmd = ['pdftoppm', '-png', '-r', str(resolution)]
        if pages:
            parts = str(pages).split('-')
            cmd.extend(['-f', parts[0]])
            if len(parts) > 1:
                cmd.extend(['-l', parts[1]])
        cmd.extend([pdf_path, output_prefix])
        subprocess.run(cmd, check=True, timeout=600)
        pngs = sorted([f for f in os.listdir(WORK_DIR) if f.startswith(job_id) and f.endswith('.png')], key=lambda x: int(''.join(c for c in x.rsplit('-',1)[-1] if c.isdigit()) or 0))
        if not pngs:
            return jsonify({'error': True, 'message': 'No PNGs generated'}), 500
        base_url = request.host_url.rstrip('/')
        urls = []
        for png in pngs:
            shutil.move(os.path.join(WORK_DIR, png), os.path.join(serve_dir, png))
            urls.append(f'{base_url}/files/{job_id}/{png}')
        return jsonify({'pageCount': len(urls), 'error': False, 'status': 200, 'urls': urls, 'credits': 0, 'remainingCredits': 999999})
    except subprocess.TimeoutExpired:
        return jsonify({'error': True, 'message': 'Conversion timed out'}), 500
    except Exception as e:
        return jsonify({'error': True, 'message': str(e)}), 500

@app.route('/files/<job_id>/<filename>')
def serve_file(job_id, filename):
    directory = os.path.join(SERVE_DIR, job_id)
    if not os.path.isdir(directory):
        return jsonify({'error': 'Files not found or expired'}), 404
    return send_from_directory(directory, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, threaded=True)

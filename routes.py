from flask import request, jsonify, send_file, render_template, Response
from app import db
from models import Project, Folder, Photo
import uuid, io, zipfile, base64


def register_routes(app):

    # ── PWA shell ──────────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/manifest.json')
    def manifest():
        return jsonify({
            "name": "Field Image Manager",
            "short_name": "FieldCam",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f0f0f",
            "theme_color": "#0f0f0f",
            "orientation": "portrait",
            "icons": [
                {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
            ]
        })

    @app.route('/sw.js')
    def service_worker():
        return app.send_static_file('js/sw.js'), 200, {
            'Content-Type': 'application/javascript'
        }

    # ── Projects ───────────────────────────────────────────────────────────────
    @app.route('/api/projects', methods=['GET'])
    def get_projects():
        projects = Project.query.order_by(Project.created_at.desc()).all()
        return jsonify([p.to_dict() for p in projects])

    @app.route('/api/projects', methods=['POST'])
    def create_project():
        data = request.get_json()
        name = (data or {}).get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        p = Project(name=name)
        db.session.add(p)
        db.session.commit()
        return jsonify(p.to_dict()), 201

    @app.route('/api/projects/<int:pid>', methods=['DELETE'])
    def delete_project(pid):
        p = Project.query.get_or_404(pid)
        db.session.delete(p)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/projects/<int:pid>/download')
    def download_project(pid):
        p       = Project.query.get_or_404(pid)
        buf     = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder in p.folders:
                for photo in folder.photos:
                    if photo.data:
                        path = f"{p.name}/{folder.name}/{photo.filename}"
                        zf.writestr(path, photo.data)
                        written += 1
        if written == 0:
            return jsonify({'error': 'No photos found'}), 404
        buf.seek(0)
        return send_file(
            buf,
            download_name=f"{p.name}.zip",
            as_attachment=True,
            mimetype='application/zip'
        )

    # ── Folders ────────────────────────────────────────────────────────────────
    @app.route('/api/projects/<int:pid>/folders', methods=['GET'])
    def get_folders(pid):
        Project.query.get_or_404(pid)
        folders = Folder.query.filter_by(project_id=pid)\
                              .order_by(Folder.created_at.asc()).all()
        return jsonify([f.to_dict() for f in folders])

    @app.route('/api/projects/<int:pid>/folders', methods=['POST'])
    def create_folder(pid):
        Project.query.get_or_404(pid)
        data = request.get_json()
        name = (data or {}).get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        f = Folder(name=name, project_id=pid)
        db.session.add(f)
        db.session.commit()
        return jsonify(f.to_dict()), 201

    @app.route('/api/folders/<int:fid>', methods=['DELETE'])
    def delete_folder(fid):
        f = Folder.query.get_or_404(fid)
        db.session.delete(f)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/folders/<int:fid>/download')
    def download_folder(fid):
        f   = Folder.query.get_or_404(fid)
        buf = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for photo in f.photos:
                if photo.data:
                    zf.writestr(photo.filename, photo.data)
                    written += 1
        if written == 0:
            return jsonify({'error': 'No photos found'}), 404
        buf.seek(0)
        return send_file(
            buf,
            download_name=f"{f.name}.zip",
            as_attachment=True,
            mimetype='application/zip'
        )

    # ── Photos ─────────────────────────────────────────────────────────────────
    @app.route('/api/folders/<int:fid>/photos', methods=['GET'])
    def get_photos(fid):
        Folder.query.get_or_404(fid)
        photos = Photo.query.filter_by(folder_id=fid)\
                            .order_by(Photo.uploaded_at.desc()).all()
        return jsonify([p.to_dict() for p in photos])

    @app.route('/api/folders/<int:fid>/photos', methods=['POST'])
    def upload_photo(fid):
        folder = Folder.query.get_or_404(fid)
        data   = request.get_json()
        if not data:
            return jsonify({'error': 'No data'}), 400

        b64      = data.get('data', '')
        filename = data.get('filename', f"{uuid.uuid4().hex[:8]}.jpg")
        mime     = data.get('mime_type', 'image/jpeg')

        try:
            raw = base64.b64decode(b64)
        except Exception:
            return jsonify({'error': 'Invalid base64'}), 400

        photo = Photo(
            filename=filename,
            folder_id=fid,
            data=raw,
            mime_type=mime,
            synced=True
        )
        db.session.add(photo)
        db.session.commit()
        return jsonify(photo.to_dict()), 201

    @app.route('/api/photos/<int:photo_id>/image')
    def get_photo_image(photo_id):
        photo = Photo.query.get_or_404(photo_id)
        if not photo.data:
            return jsonify({'error': 'No image data'}), 404
        return Response(photo.data, mimetype=photo.mime_type)

    @app.route('/api/photos/<int:photo_id>', methods=['DELETE'])
    def delete_photo(photo_id):
        photo = Photo.query.get_or_404(photo_id)
        db.session.delete(photo)
        db.session.commit()
        return jsonify({'ok': True})

    # ── Bulk sync from IndexedDB queue ────────────────────────────────────────
    @app.route('/api/sync', methods=['POST'])
    def sync_photos():
        data  = request.get_json()
        items = (data or {}).get('items', [])
        results = []

        for item in items:
            fid      = item.get('folder_id')
            filename = item.get('filename', 'photo.jpg')
            mime     = item.get('mime_type', 'image/jpeg')
            b64      = item.get('data', '')

            folder = Folder.query.get(fid)
            if not folder:
                results.append({'filename': filename, 'status': 'error', 'reason': 'Folder not found'})
                continue
            try:
                raw = base64.b64decode(b64)
            except Exception:
                results.append({'filename': filename, 'status': 'error', 'reason': 'Bad data'})
                continue

            photo = Photo(filename=filename, folder_id=fid, data=raw, mime_type=mime, synced=True)
            db.session.add(photo)
            results.append({'filename': filename, 'status': 'synced'})

        db.session.commit()
        return jsonify({'results': results})

    # ── Health check (Railway needs this) ─────────────────────────────────────
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

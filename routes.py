from flask import request, jsonify, send_file, render_template, Response
from app import db
from models import Project, Folder, Photo
from r2_service import upload_to_r2, download_from_r2, delete_from_r2, R2_CONFIGURED
import uuid, io, zipfile, base64


def make_thumbnail(raw_bytes: bytes, max_kb: int = 200) -> bytes:
    """
    Compress image to approximately max_kb kilobytes using Pillow.
    Falls back to original if Pillow not available.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw_bytes))

        # Convert RGBA/P to RGB for JPEG compatibility
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')

        # Resize — cap longest side at 1200px for 200KB target
        max_side = 1200
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        # Binary search for quality that hits ~200KB
        lo, hi, quality = 20, 90, 70
        buf = io.BytesIO()
        for _ in range(6):
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            size_kb = buf.tell() / 1024
            if size_kb > max_kb * 1.05:
                hi = quality - 1
            elif size_kb < max_kb * 0.80:
                lo = quality + 1
            else:
                break
            quality = (lo + hi) // 2

        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f'Thumbnail generation failed: {e}')
        return raw_bytes  # fallback to original


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

    @app.route('/api/projects/<int:pid>', methods=['PATCH'])
    def rename_project(pid):
        p    = Project.query.get_or_404(pid)
        data = request.get_json()
        name = (data or {}).get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        p.name = name
        db.session.commit()
        return jsonify(p.to_dict())

    @app.route('/api/projects/<int:pid>', methods=['DELETE'])
    def delete_project(pid):
        p = Project.query.get_or_404(pid)
        # Delete all R2 files for this project
        for folder in p.folders:
            for photo in folder.photos:
                if photo.r2_key:
                    delete_from_r2(photo.r2_key)
        db.session.delete(p)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/projects/<int:pid>/download')
    def download_project(pid):
        """ZIP of full-quality images from R2, falls back to thumbnails."""
        p   = Project.query.get_or_404(pid)
        buf = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for folder in p.folders:
                for photo in folder.photos:
                    data = None
                    if photo.r2_key:
                        data = download_from_r2(photo.r2_key)
                    if data is None and photo.thumbnail:
                        data = photo.thumbnail  # fallback to preview
                    if data:
                        path = f"{p.name}/{folder.name}/{photo.filename}"
                        zf.writestr(path, data)
                        written += 1
        if written == 0:
            return jsonify({'error': 'No photos found'}), 404
        buf.seek(0)
        return send_file(buf, download_name=f"{p.name}.zip",
                         as_attachment=True, mimetype='application/zip')

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

    @app.route('/api/folders/<int:fid>', methods=['PATCH'])
    def rename_folder(fid):
        f    = Folder.query.get_or_404(fid)
        data = request.get_json()
        name = (data or {}).get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name required'}), 400
        f.name = name
        db.session.commit()
        return jsonify(f.to_dict())

    @app.route('/api/folders/<int:fid>', methods=['DELETE'])
    def delete_folder(fid):
        f = Folder.query.get_or_404(fid)
        for photo in f.photos:
            if photo.r2_key:
                delete_from_r2(photo.r2_key)
        db.session.delete(f)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/folders/<int:fid>/download')
    def download_folder(fid):
        """ZIP of full-quality images from R2, falls back to thumbnails."""
        f   = Folder.query.get_or_404(fid)
        buf = io.BytesIO()
        written = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for photo in f.photos:
                data = None
                if photo.r2_key:
                    data = download_from_r2(photo.r2_key)
                if data is None and photo.thumbnail:
                    data = photo.thumbnail
                if data:
                    zf.writestr(photo.filename, data)
                    written += 1
        if written == 0:
            return jsonify({'error': 'No photos found'}), 404
        buf.seek(0)
        return send_file(buf, download_name=f"{f.name}.zip",
                         as_attachment=True, mimetype='application/zip')

    # ── Photos ─────────────────────────────────────────────────────────────────
    @app.route('/api/folders/<int:fid>/photos', methods=['GET'])
    def get_photos(fid):
        Folder.query.get_or_404(fid)
        photos = Photo.query.filter_by(folder_id=fid)\
                            .order_by(Photo.uploaded_at.desc()).all()
        return jsonify([p.to_dict() for p in photos])

    @app.route('/api/folders/<int:fid>/photos', methods=['POST'])
    def upload_photo(fid):
        """
        Receives base64 photo from frontend.
        1. Generates 200KB thumbnail → saves to PostgreSQL immediately
        2. Uploads full quality → R2 in same request (fast enough for most connections)
        Returns immediately after thumbnail is saved so UI feels instant.
        """
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

        # 1. Generate thumbnail
        thumb = make_thumbnail(raw, max_kb=200)

        # 2. Build R2 key: ProjectName/FolderName/filename
        project = Project.query.get(folder.project_id)
        r2_key  = f"{project.name}/{folder.name}/{filename}"

        # 3. Save photo record with thumbnail immediately
        photo = Photo(
            filename=filename,
            folder_id=fid,
            thumbnail=thumb,
            mime_type=mime,
            r2_key=r2_key,
            synced=True,
            r2_uploaded=False,
        )
        db.session.add(photo)
        db.session.commit()

        # 4. Upload full quality to R2
        if R2_CONFIGURED:
            success = upload_to_r2(raw, r2_key, mime)
            if success:
                photo.r2_uploaded = True
                db.session.commit()

        return jsonify(photo.to_dict()), 201

    @app.route('/api/photos/<int:photo_id>/preview')
    def get_photo_preview(photo_id):
        """Serve the 200KB thumbnail from PostgreSQL — fast."""
        photo = Photo.query.get_or_404(photo_id)
        if not photo.thumbnail:
            return jsonify({'error': 'No preview'}), 404
        return Response(photo.thumbnail, mimetype='image/jpeg',
                        headers={'Cache-Control': 'public, max-age=86400'})

    @app.route('/api/photos/<int:photo_id>/full')
    def get_photo_full(photo_id):
        """Serve full-quality image from R2. Used only on download."""
        photo = Photo.query.get_or_404(photo_id)
        if photo.r2_key and photo.r2_uploaded:
            data = download_from_r2(photo.r2_key)
            if data:
                return Response(data, mimetype=photo.mime_type,
                                headers={'Cache-Control': 'public, max-age=86400'})
        # Fallback to thumbnail if R2 not available
        if photo.thumbnail:
            return Response(photo.thumbnail, mimetype='image/jpeg')
        return jsonify({'error': 'No image data'}), 404

    @app.route('/api/photos/<int:photo_id>', methods=['DELETE'])
    def delete_photo(photo_id):
        photo = Photo.query.get_or_404(photo_id)
        if photo.r2_key:
            delete_from_r2(photo.r2_key)
        db.session.delete(photo)
        db.session.commit()
        return jsonify({'ok': True})

    # ── Bulk sync from IndexedDB ───────────────────────────────────────────────
    @app.route('/api/sync', methods=['POST'])
    def sync_photos():
        data    = request.get_json()
        items   = (data or {}).get('items', [])
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

            thumb   = make_thumbnail(raw, max_kb=200)
            project = Project.query.get(folder.project_id)
            r2_key  = f"{project.name}/{folder.name}/{filename}"

            photo = Photo(
                filename=filename, folder_id=fid,
                thumbnail=thumb, mime_type=mime,
                r2_key=r2_key, synced=True, r2_uploaded=False,
            )
            db.session.add(photo)
            db.session.flush()

            if R2_CONFIGURED:
                success = upload_to_r2(raw, r2_key, mime)
                photo.r2_uploaded = success

            results.append({'filename': filename, 'status': 'synced'})

        db.session.commit()
        return jsonify({'results': results})

    # ── R2 status ─────────────────────────────────────────────────────────────
    @app.route('/api/status')
    def status():
        return jsonify({'r2_configured': R2_CONFIGURED})

    # ── Health ────────────────────────────────────────────────────────────────
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

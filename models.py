from app import db
from datetime import datetime


class Project(db.Model):
    __tablename__ = 'projects'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    folders    = db.relationship('Folder', backref='project', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'created_at':    self.created_at.isoformat(),
            'folder_count':  len(self.folders),
            'photo_count':   sum(len(f.photos) for f in self.folders),
            'synced_count':  sum(sum(1 for p in f.photos if p.synced)  for f in self.folders),
            'offline_count': sum(sum(1 for p in f.photos if not p.synced) for f in self.folders),
            'folder_previews': [{'id': f.id, 'name': f.name} for f in self.folders[:3]],
        }


class Folder(db.Model):
    __tablename__ = 'folders'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos     = db.relationship('Photo', backref='folder', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'project_id':    self.project_id,
            'created_at':    self.created_at.isoformat(),
            'photo_count':   len(self.photos),
            'synced_count':  sum(1 for p in self.photos if p.synced),
            'offline_count': sum(1 for p in self.photos if not p.synced),
        }


class Photo(db.Model):
    __tablename__ = 'photos'
    id            = db.Column(db.Integer, primary_key=True)
    filename      = db.Column(db.String(300), nullable=False)
    folder_id     = db.Column(db.Integer, db.ForeignKey('folders.id'), nullable=False)
    synced        = db.Column(db.Boolean, default=False)
    mime_type     = db.Column(db.String(50), default='image/jpeg')
    uploaded_at   = db.Column(db.DateTime, default=datetime.utcnow)

    # 200KB compressed preview — stored in PostgreSQL for fast loading
    thumbnail     = db.Column(db.LargeBinary, nullable=True)

    # R2 key for full-quality original e.g. "ProjectName/FolderName/photo.jpg"
    r2_key        = db.Column(db.String(500), nullable=True)

    # True once full image is uploaded to R2
    r2_uploaded   = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id':          self.id,
            'filename':    self.filename,
            'folder_id':   self.folder_id,
            'synced':      self.synced,
            'mime_type':   self.mime_type,
            'uploaded_at': self.uploaded_at.isoformat(),
            'r2_uploaded': self.r2_uploaded,
            'has_preview': self.thumbnail is not None,
        }

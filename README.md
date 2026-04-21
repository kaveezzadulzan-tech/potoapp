# FieldCam — Field Image Manager

Mobile-first PWA for capturing and organising site photos.
Dark mode · Offline-first · Railway backend · Installable on Android.

---

## File structure
```
fieldcam/
├── app.py           ← Flask entry point
├── models.py        ← DB models (Project, Folder, Photo)
├── routes.py        ← All API endpoints
├── requirements.txt
├── Procfile         ← Railway start command
├── railway.toml     ← Railway config
├── templates/
│   └── index.html   ← Full PWA frontend
└── static/
    └── js/
        └── sw.js    ← Service worker
```

---

## Local development

```bash
pip install -r requirements.txt
python app.py
# Visit http://localhost:5001
```

---

## Deploy to Railway (free)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "initial commit"
# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/fieldcam.git
git push -u origin main
```

### Step 2 — Create Railway project
1. Go to railway.app → New Project
2. Deploy from GitHub repo → select your repo
3. Railway auto-detects Python and deploys

### Step 3 — Add PostgreSQL
1. In Railway dashboard → + New → Database → PostgreSQL
2. Railway automatically sets `DATABASE_URL` environment variable
3. Your app reads it automatically — nothing to configure

### Step 4 — Add SECRET_KEY
1. In Railway → your service → Variables
2. Add: `SECRET_KEY` = any long random string

### Step 5 — Get your URL
Railway gives you a URL like:  `https://fieldcam-production.up.railway.app`

---

## Install as Android app

1. Open Chrome on your Android phone
2. Go to your Railway URL
3. Chrome shows "Add to Home screen" banner — tap it
4. Or: Chrome menu (⋮) → "Add to Home screen"
5. App icon appears on your home screen
6. Opens full screen, no browser bar — feels native

---

## How offline works

| Situation | What happens |
|-----------|-------------|
| Online | Photos upload directly to Railway on capture |
| Offline | Photos save to browser IndexedDB queue |
| Back online | Go to Sync tab → tap "Sync" |
| Server down | App still works, queue stores locally |

---

## Architecture

```
Android Chrome (PWA)
  ├── Service Worker  → caches app shell for offline
  ├── IndexedDB       → stores offline photo queue
  └── File System API → not needed (Railway stores photos)

Railway (Flask + PostgreSQL)
  ├── /api/projects   → CRUD
  ├── /api/folders    → CRUD
  ├── /api/photos     → upload, view, delete
  ├── /api/sync       → bulk push from offline queue
  └── /api/.../download → ZIP export
```

---

## Notes

- Photos are stored as binary in PostgreSQL on Railway
- Free Railway tier: 5 USD credit/month — enough for personal use
- ZIP download works for entire project or individual folder
- Delete long-press on photo thumbnails to delete individual photos

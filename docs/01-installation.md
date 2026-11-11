<div dir="rtl">

# 1) التثبيت والنشر

## المتطلبات

| المكوّن | الحد الأدنى | ملاحظات |
| --- | --- | --- |
| Python | 3.11+ | يعمل على 3.12/3.13 |
| PostgreSQL | 14+ | يحتاج امتداد `pg_trgm` للبحث السريع (موجود افتراضياً في صور Docker) |
| Node.js | 20+ | **اختياري** — فقط إذا أردت إعادة بناء الواجهة؛ نسخة مبنية مسبقاً مرفقة |
| مساحة القرص | ~1 GB | معظمها حزمة متصفح Camoufox (~200MB) |

## الطريقة 1: Docker (الموصى بها للإنتاج)

```bash
# 1. جهّز ملف البيئة
cp .env.example .env
```

عدّل في `.env`:

```ini
XFOX_SECRET_KEY=<شغّل: python -c "import secrets;print(secrets.token_urlsafe(48))">
XFOX_DB_PASSWORD=<كلمة مرور قوية لقاعدة البيانات>
```

```bash
# 2. شغّل المكدس كاملاً (التطبيق + PostgreSQL)
docker compose -f docker/docker-compose.yml up -d --build

# 3. تابع السجلات حتى يجهز
docker compose -f docker/docker-compose.yml logs -f xfox
```

افتح `http://localhost:8000`.

- الترحيلات تُطبَّق تلقائياً عند كل إقلاع (entrypoint).
- البيانات في مجلدين دائمين: `postgres-data` (القاعدة) و `app-data` (مساحات العمل والتصديرات والسجلات).

**تغيير المنفذ:** أضف `XFOX_PORT=9000` في `.env` قبل التشغيل.

## الطريقة 2: تثبيت مباشر

### Linux / macOS

```bash
./scripts/setup.sh
```

يقوم السكربت بكل شيء: بيئة افتراضية، تثبيت الحزم (ومنها x-crawlfox)، تنزيل متصفح Camoufox، توليد `.env` بمفتاح سري، بناء الواجهة (إن وُجد Node)، وتطبيق ترحيلات القاعدة.

```bash
./scripts/run.sh        # أو: make run
```

### Windows

```bat
scripts\setup.bat
scripts\run.bat
```

### الإعداد اليدوي (للمدققين)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
camoufox fetch                                   # تنزيل المتصفح (مرة واحدة)
cp .env.example .env    # ثم عدّل المفاتيح
alembic upgrade head                             # ترحيل القاعدة
(cd web && npm install && npm run build)         # الواجهة (اختياري)
uvicorn xfox.main:app --host 0.0.0.0 --port 8000
```

## خلف Nginx (HTTPS)

```nginx
server {
    listen 443 ssl;
    server_name harvester.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # SSE: لا تُغلّق الاتصالات المفتوحة
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

> عند التشغيل خلف HTTPS اضبط `XFOX_COOKIE_SECURE=true` في `.env` حتى تُرسَل كوكيز الجلسة مشفرة فقط.

## التشغيل كخدمة نظام (systemd)

```bash
sudo cp deploy/xfox-harvester.service /etc/systemd/system/
# عدّل داخل الملف: User= و WorkingDirectory= و مسار .env
sudo systemctl daemon-reload
sudo systemctl enable --now xfox-harvester
journalctl -u xfox-harvester -f
```

## الترقية

```bash
# Docker
docker compose -f docker/docker-compose.yml pull --ignore-buildable 2>/dev/null
docker compose -f docker/docker-compose.yml up -d --build

# مباشر
git pull && pip install -e . && alembic upgrade head \
  && (cd web && npm install && npm run build) && sudo systemctl restart xfox-harvester
```

## النسخ الاحتياطي

- **القاعدة:** `pg_dump -U xfox xfox > backup-$(date +%F).sql`
- **البيانات:** أرشفة مجلد `data/` كاملاً (يحتوي كوكيز الحسابات في `data/accounts/` — **حسّاس، لا ترفعه لمكان عام**).

</div>

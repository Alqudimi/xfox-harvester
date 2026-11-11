<div dir="rtl">

# 🦊 XFox Harvester

**منصة إنتاجية متكاملة لحصد منشورات X (تويتر سابقاً) بأمان — مبنية فوق محرك [X-CrawlFox](https://github.com/Jiutwo/x-crawlfox) وتُدار بالكامل من واجهة ويب رسومية.**

النظام يحيط أداة X-CrawlFox (المتصفح المضاد للبصمات Camoufox مع سلوك بشري مُحاكى) بطبقة حَوْكَمة كاملة للحماية من الحظر: توزيع متعدد الحسابات، تباعد وتذبذب عشوائي، تهدئة تلقائية، تراجع أسي، مراقب مخاطر عام (أخضر/أصفر/أحمر)، جدولة ذكية، تخزين PostgreSQL، بحث فوري، تصدير CSV/JSON/Excel، وأحداث مباشرة عبر SSE — كل ذلك بواجهة عربية RTL مع تبديل فوري للإنجليزية.

---

## ✨ المزايا

| المجال | ما تحصل عليه |
| --- | --- |
| **حماية من الحظر** | تباعد أدنى بين التشغيلات (لكل حساب وعالمياً) مع تذبذب عشوائي، سقوف يومية، إحماء للحسابات الجديدة، تهدئة بعد قيود المعدل أو النتائج الفارغة، تعطيل تلقائي عند تدهور الصحة، مقياس مخاطر عام يوقف المحرك عند الخطر الأحمر |
| **متعدد الحسابات** | كل حساب X في مساحة عمل معزولة (كوكيز + حالة تزايدية مستقلة) مع بروكسي ثابت لكل حساب واختبار حي للجلسة |
| **كل عمليات المحرك** | بحث بالكلمات المفتاحية (بكتابة بشرية)، مراقبة حسابات تزايدياً، الخط الزمني (Following/For you)، أخبار اليوم مع ملخصات Grok، ومهام مركّبة — كلها عبر أمر `x all` الموحّد |
| **واجهة رسومية كاملة** | لوحة قيادة إحصائية، معالج إنشاء مهام من 5 خطوات، مستكشف منشورات بفلاتر متقدمة، سجل حي، إعدادات عميقة لكل سياسة، إدارة مستخدمين بأدوار |
| **بيانات جاهزة للتحليل** | PostgreSQL مع JSONB وفهارس trigram للبحث العربي/الإنجليزي الفوري، تصدير خلفي بثلاث صيغ |
| **إنتاج جاهز** | Docker + docker-compose، سكربتات تثبيت لنظامي Linux/Windows، وحدة systemd، اختبارات موثّقة (73+)، وثائق عربية شاملة |

## 🚀 التشغيل السريع

### الخيار 1: Docker (الأسهل)

```bash
# 1) انسخ المشروع واضبط المفاتيح
cp .env.example .env
#   عدّل: XFOX_SECRET_KEY و XFOX_DB_PASSWORD

# 2) شغّل كل شيء
docker compose -f docker/docker-compose.yml up -d --build

# 3) افتح اللوحة
# http://localhost:8000
```

### الخيار 2: تثبيت مباشر (Linux/macOS)

```bash
./scripts/setup.sh     # بيئة افتراضية + متصفح Camoufox + .env + بناء الواجهة + ترحيل قاعدة البيانات
./scripts/run.sh       # http://localhost:8000
```

على Windows: `scripts\setup.bat` ثم `scripts\run.bat`

> **المتطلبات:** Python 3.11+ و PostgreSQL و (اختياري لبناء الواجهة) Node.js 20+
> تُحمَّل حزمة متصفح Camoufox (~200MB) مرة واحدة أثناء الإعداد.

### أول 3 دقائق داخل اللوحة

1. **إنشاء المدير** — عند أول فتح تظهر شاشة إعداد حساب المدير.
2. **إضافة حساب X** — من صفحة «حسابات X»: أضف حساباً ثم ارفع كوكيزه عبر إضافة [Cookie Editor](https://cookie-editor.com) (Export ← JSON)، واضغط «اختبار الحساب».
3. **إنشاء مهمة** — من «مهام الحصد»: معالج من 5 خطوات (النوع ← الإعدادات ← الجدولة ← سياسة الأمان ← المراجعة) ثم «تشغيل الآن» وراقب السجل الحي.

## 🗂️ هيكل المشروع

```
xfox-harvester/
├── xfox/                  # الطبقة الخلفية (Python)
│   ├── domain/            #   المفردات + سياسات الحماية (منطق نقي قابل للاختبار)
│   ├── db/                #   نماذج SQLAlchemy + مستودعات الوصول للبيانات
│   ├── engine/            #   المحرك: منسّق، مجمّع حسابات، مخاطر، محوّل X-CrawlFox…
│   ├── api/               #   مسارات FastAPI (RBAC + SSE)
│   └── main.py            #   نقطة الدخول
├── web/                   # واجهة React + Vite + Tailwind (عربية RTL / إنجليزية)
├── migrations/            # ترحيلات Alembic
├── docker/                # Dockerfile + docker-compose + entrypoint
├── scripts/               # setup/run للينكس والويندوز
├── deploy/                # وحدة systemd
├── tests/                 # 73+ اختباراً (سياسات، تصنيف، استيعاب، API)
└── docs/                  # وثائق عربية مفصّلة
```

## 📚 الوثائق

| الدليل | المحتوى |
| --- | --- |
| [التثبيت والنشر](docs/01-installation.md) | المتطلبات، Docker، التثبيت المباشر، systemd، الترقية |
| [المعمارية](docs/02-architecture.md) | الطبقات، تدفق التشغيل، قرارات التصميم |
| [الحماية من الحظر](docs/03-anti-ban.md) | كيف يعمل خط الدفاع المزدوج — شرح كل سياسة |
| [دليل الاستخدام](docs/04-usage.md) | كل شاشة وكل عملية بالتفصيل |
| [مرجع API](docs/05-api.md) | كل نقاط النهاية مع أمثلة curl |
| [استكشاف الأخطاء](docs/06-troubleshooting.md) | المشاكل الشائعة وحلولها |

## 🔐 الأدوار

| الدور | الصلاحيات |
| --- | --- |
| **مدير** | كل شيء + إدارة المستخدمين والإعدادات ومنطقة الخطر |
| **مشغّل** | الحسابات والمهام والبروكسيات والتصدير — بدون إدارة مستخدمين |
| **مشاهد** | عرض فقط |

## ⚠️ إخلاء مسؤولية

الأداة لأغراض تعليمية وبحثية. الالتزام باتفاقية شروط خدمة X مسؤوليتك — استخدم حسابات لا تخاف عليها، وفعّل الوتيرة «الحذرة» في البداية، وراقب مقياس المخاطر.

</div>

---

<div dir="ltr">

# XFox Harvester (English)

A production-grade orchestration platform around [X-CrawlFox](https://github.com/Jiutwo/x-crawlfox) for safely harvesting X (Twitter) posts. X-CrawlFox provides the anti-fingerprint Camoufox browser with humanized browsing; XFox Harvester adds the governance layer: multi-account pooling with isolated workspaces, jittered pacing, cooldowns, exponential backoff, a global GREEN/YELLOW/RED risk gauge that pauses the engine when X pushes back, scheduling with active-hours windows, PostgreSQL storage with instant Arabic/English search, CSV/JSON/XLSX exports, live SSE events, and a full bilingual (Arabic-first, RTL) web console with role-based access control.

```bash
# Docker (recommended)
cp .env.example .env    # set XFOX_SECRET_KEY + XFOX_DB_PASSWORD
docker compose -f docker/docker-compose.yml up -d --build

# or direct install
./scripts/setup.sh && ./scripts/run.sh
```

Open http://localhost:8000 — create the admin account, add an X account with its Cookie-Editor export, then launch your first harvest job from the 5-step wizard.

**Stack:** FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · React 18 · Vite · Tailwind CSS 4 · Recharts · X-CrawlFox · Camoufox

**Docs:** [installation](docs/01-installation.md) · [architecture](docs/02-architecture.md) · [anti-ban](docs/03-anti-ban.md) · [usage](docs/04-usage.md) · [API](docs/05-api.md) · [troubleshooting](docs/06-troubleshooting.md)

> For educational and research purposes. You are responsible for complying with X's Terms of Service.

</div>

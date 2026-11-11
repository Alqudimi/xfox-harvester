<div dir="rtl">

# 5) مرجع REST API

**الأساس:** `http://localhost:8000/api` — المصادقة بكوكي `xfox_session` (JWT).
**التوثيق التفاعلي:** `http://localhost:8000/api/docs` (OpenAPI مولّد تلقائياً).

> كل نقاط النهاية محمية بالأدوار: 🔴 مدير فقط · 🟡 مشغل+ · 🟢 أي مستخدم مسجّل. البادئة `P` تعني POST و `G` GET و `U` PUT و `PA` PATCH و `D` DELETE.

## المصادقة

| طلب | المسار | ملاحظات |
| --- | --- | --- |
| G | `/auth/bootstrap-status` | هل أُنشئ المدير؟ (يوجه الواجهة لشاشة الإعداد) |
| P | `/auth/setup` | إنشاء المدير الأول — يُرفض بعد أول مرة (409) |
| P | `/auth/login` | `{username, password}` → كوكي جلسة (حد 5 محاولات/5 د) |
| P | `/auth/logout` | مسح الجلسة |
| G | `/auth/me` | بيانات المستخدم الحالي |
| P | `/auth/change-password` | `{current_password, new_password}` |

## المستخدمون 🔴

```
G  /users                 قائمة المستخدمين
P  /users                 {username, password, role: admin|operator|viewer, display_name?}
PA /users/{id}            {role?, is_active?, password?, display_name?}
D  /users/{id}            (يُرفض حذف النفس — 400)
```

## حسابات X 🟡 إدارة / 🟢 عرض

```
G  /accounts                         قائمة مع الصحة والإحصاءات
P  /accounts                         {label, notes?, proxy_id?}
PA /accounts/{id}                    {label?, notes?, proxy_id?, status?}
D  /accounts/{id}                    يحذف مساحة العمل كاملة
P  /accounts/{id}/cookies            {content: "<Cookie-Editor JSON>"}  → تحقق + تثبيت
P  /accounts/{id}/test               اختبار حي (حتى ~دقيقتين) → {outcome, collected, duration_ms}
```

## البروكسيات 🟡 إدارة / 🟢 عرض

```
G  /proxies                          قائمة مع آخر فحص
P  /proxies                          {url, label?}
PA /proxies/{id}                     {url?, label?, status?}
D  /proxies/{id}
P  /proxies/{id}/check               فحص حي → {ok, latency_ms, error?}
```

## المهام والتشغيلات 🟡 إدارة / 🟢 عرض

```
G  /jobs                             قائمة المهام
P  /jobs                             إنشاء (انظر المثال أدناه)
G  /jobs/{id} · PA /jobs/{id} · D /jobs/{id}
P  /jobs/{id}/action                 {action: "run_now"|"pause"|"resume"}
G  /jobs/{id}/runs?page=&page_size=  سجل تشغيلات المهمة
G  /runs?job_id=&status_filter=&page=كل التشغيلات
G  /runs/{id} · G /runs/{id}/log     تفاصيل + السجل الكامل
P  /runs/{id}/cancel 🟡              إلغاء تشغيل (يقتل المتصفح)
```

**مثال إنشاء مهمة مراقبة:**

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' -b cookies.txt \
  -d '{
    "name": "مراقبة التقنية",
    "type": "monitor",
    "config": {
      "monitor": {
        "users": [
          {"username": "elonmusk", "only_new": true, "max_tweets": 10},
          {"username": "OpenAI",   "only_new": true, "max_tweets": 10}
        ],
        "global_max": 100
      }
    },
    "schedule": {"kind": "interval", "interval_minutes": 120},
    "anti_ban": {"aggressiveness": "cautious"},
    "priority": 7
  }'
```

**مثال مهمة بحث:**

```json
{
  "name": "رصد الذكاء الاصطناعي",
  "type": "search",
  "config": {"search": {"keywords": ["الذكاء الاصطناعي", "AGI"], "max_items_per_keyword": 20}},
  "schedule": {"kind": "daily", "daily_at": "09:00"}
}
```

## البيانات 🟢

```
G /data/posts?q=&author=&sources=&date_from=&date_to=&min_likes=&min_views=
             &has_media=&sort=likes&order=desc&page=1&page_size=25
G /data/authors?q=&page=&page_size=
G /data/sources                    قيم المصادر المتاحة للفلترة
```

## التصدير 🟡

```
P /exports             {entity: posts|authors, format: csv|json|xlsx, filters: {…}}
G /exports             قائمة التصديرات
G /exports/{id}        حالة صف التصدير
G /exports/{id}/download   تنزيل الملف (جاهز بعد status=done)
```

## الأحداث 🟢

```
G /events?level=&category=&q=&page=&page_size=   السجل التاريخي
G /events/stream?category=&level=                البث الحي (SSE — EventSource)
```

كل رسالة SSE: `{"id","ts","type","level","category","message","params","account_id","job_id","run_id"}`

## الإعدادات والنظام

```
G  /settings 🟢        قراءة كل السياسات
U  /settings 🔴        استبدال موثّق (يسري فوراً)
G  /system/overview 🟢 لوحة القيادة (مجاميع، اليوم، خطر، 14 يوماً، أعلى المؤلفين، آخر التشغيلات)
G  /system/status  🟢 صحة النظام (محرك/متصفح/قاعدة/قرص/مدة التشغيل)
P  /system/risk/acknowledge 🟡  إقرار الخطر الأحمر واستئناف المحرك
P  /system/maintenance/purge 🔴 تنظيف حسب سياسة الاحتفاظ
D  /system/data/posts?confirm=DELETE 🔴 حذف كل البيانات المحصودة
```

## أكواد الأخطاء الشائعة

| الرمز | المعنى |
| --- | --- |
| `not_authenticated` / 401 | لا جلسة — أعد الدخول |
| `permission_denied` / 403 | دورك لا يملك هذه الصلاحية |
| `run_already_active` / 409 | للمهمة تشغيل قائم بالفعل |
| `no_cookies_installed` / 400 | اختبار حساب بلا كوكيز |
| `no_x_domain_cookie_found` / 400 | كوكيز ليست لجلسة x.com |
| `too_many_attempts` / 429 | قفل مؤقت لتكرار محاولات الدخول |

</div>

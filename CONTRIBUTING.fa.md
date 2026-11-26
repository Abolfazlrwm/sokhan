# مشارکت در سخن

[English](CONTRIBUTING.md) | **فارسی**

ممنون که به سخن سر زدید. این مخزن یک کیت گفتار به متنِ فارسی است که
می‌شود سلف‌هاستش کرد: یک بک‌اند FastAPI با موتور faster-whisper، یک ورکر
Celery، یک داشبورد Next.js (فارسی‌محور و راست‌به‌چپ)، یک ربات تلگرام
اختیاری، یک پایپ‌لاین فاین‌تیونِ LoRA با نتایجِ اندازه‌گیری‌شده، و یک دموی
عمومیِ مرورگری روی Hugging Face.

## راه‌اندازی محیط توسعه

برای بک‌اند و ربات Python 3.12 و برای داشبورد وب Node 22 لازم است:

    pip install -e "backend[dev]" -e "bot[dev]"
    cd web && npm ci

وابستگی‌های سنگین (torch / faster-whisper) فقط برای ابزارهای آموزش و
بنچمارک لازم‌اند:

    pip install -r training/requirements.txt -r benchmarks/requirements.txt
    pip install -r space/gradio/requirements.txt   # self-hostable Gradio demo

## تست‌ها، لینت و نظم کامیت‌ها

CI روی هر push و pull request همین دستورها را اجرا می‌کند:

    ruff check backend bot training benchmarks space deploy
    mypy --config-file backend/pyproject.toml backend/sokhan
    pytest backend/tests bot/tests
    cd web && npm ci && npm run build

هوک‌های pre-commit (ruff به‌علاوهٔ چند بررسی پایه) را برای هر کلون یک بار
فعال کنید:

    pip install pre-commit && pre-commit install

پیام کامیت‌ها از Conventional Commits پیروی می‌کنند (`feat:`، `fix:`،
`docs:`، ...) و نسخه‌گذاری پروژه بر اساس Semantic Versioning است؛ هر
تغییری که کاربر می‌بیند یک خط در CHANGELOG.md می‌گیرد.

## دموی مرورگری و ورک‌فلوی sync-space

`space/` دموی استاتیکی است که Whisper در آن کاملاً سمتِ مرورگر اجرا
می‌شود (transformers.js). ورک‌فلوی `Sync demo Space` با هر push‌ای که به
`space/` دست بزند، آن را با سکرتِ `HF_TOKEN` در Actions مخزن روی
hf.co/spaces/Abol0pati/sokhan-fa-demo منتشر می‌کند - برای همین دموی
عمومی هیچ‌وقت از `main` عقب نمی‌ماند. `space/gradio/` یک اپ جدا و
سلف‌هاست‌شدنی است که چک‌پوینتِ فاین‌تیون‌شده را با همان تنظیمات موتورِ
محیط production سرو می‌کند؛ این اپ عمداً روی Space عمومی آپلود نمی‌شود
(قیمت‌گذاری ۲۰۲۶ هاگینگ‌فیس، Spaceهای میزبانی‌شدهٔ Gradio/Docker را پشت
اشتراک PRO قفل کرده است).

## قاعدهٔ «اول اندازه‌گیری»

هر ادعایی دربارهٔ دقت (WER، CER، سرعت) که در README، کارت مدل یا
changelog می‌آید باید از `benchmarks/benchmark_wer.py` (یا ارزیابیِ
نوت‌بوک) آمده باشد و فیکسچر و سخت‌افزارش ذکر شده باشد. هیچ عددِ ساختگی
پذیرفته نیست.

## امنیت

گزارش‌های امنیتی را به‌صورت issue عمومی باز نکنید - برای افشای خصوصی
SECURITY.md را ببینید.

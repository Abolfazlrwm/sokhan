"""User-facing strings. The bot speaks Persian; these stay in one place."""

WELCOME = (
    "سلام! من سخن هستم.\n\n"
    "پیام صوتی یا فایل را برایم بفرست تا متن رونویسی‌شده را برایت بنویسم و "
    "خلاصهٔ کوتاهش را هم کنارش بدهم.\n\n"
    "دستورها:\n"
    "/quota — دیدن سهمیهٔ رایگان این ماه\n"
    "/track <شناسه> — دنبال کردن وضعیت یک پردازش\n\n"
    "برای اتصال حساب وب، این کد را در صفحهٔ ورود سخن وارد کن:\n{connect_code}"
)

VOICE_RECEIVED = "دریافت شد! در صف پردازش گذاشتم؛ به‌محض آماده شدن، متن را می‌فرستم."

JOB_FAILED = "پردازش این فایل ناموفق بود: {error}"

SUMMARY_BUTTON = "خلاصه"
WEB_ARCHIVE_BUTTON = "مشاهده در وب"

SUMMARY_NOT_READY = "خلاصه هنوز آماده نیست؛ کمی بعد دوباره امتحان کن."
SUMMARY_DISABLED = "خلاصه‌سازی روی این سرور فعال نیست."

STATUS_LINE = "وضعیت: {status}\nپیشرفت: {progress}٪"

QUOTA_LINE = (
    "مصرف این ماه: {used} دقیقه از {limit} دقیقه.\nباقی‌مانده: {remaining} دقیقه."
)

UNKNOWN_JOB = "چنین پردازشی پیدا نشد."

NEED_START = "اول با /start حساب را وصل کن."

QUOTA_EXHAUSTED = "سهمیهٔ رایگان ماهانه تمام شده است؛ از ابتدای ماهٔ بعد دوباره می‌توانی استفاده کنی."

RATE_LIMITED = "کمی آهسته‌تر! لطفاً چند ثانیهٔ دیگر دوباره امتحان کن."

SERVER_UNREACHABLE = "اتصال به سرور سخن برقرار نشد؛ کمی بعد دوباره امتحان کن."

DOWNLOAD_FAILED = "دانلود فایل ممکن نشد؛ دوباره امتحان کن."

STATUS_LABELS = {
    "queued": "در صف",
    "processing": "در حال پردازش",
    "completed": "آماده",
    "failed": "ناموفق",
}

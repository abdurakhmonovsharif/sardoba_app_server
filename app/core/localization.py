import re


_RATE_LIMIT_PATTERN = re.compile(r"^Ko'p so'rov jonatildi, (\d+) daqiqadan keyin yana urinib ko'ring\.$")

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "Not authenticated": {
        "uz": "Siz tizimga kirmagansiz.",
        "ru": "Вы не авторизованы.",
    },
    "Invalid authentication scheme": {
        "uz": "Avtorizatsiya usuli noto'g'ri.",
        "ru": "Неверная схема аутентификации.",
    },
    "Invalid token": {
        "uz": "Token yaroqsiz.",
        "ru": "Недействительный токен.",
    },
    "Insufficient permissions": {
        "uz": "Sizda bu amal uchun ruxsat yo'q.",
        "ru": "Недостаточно прав.",
    },
    "User not found": {
        "uz": "Foydalanuvchi topilmadi.",
        "ru": "Пользователь не найден.",
    },
    "Staff not found": {
        "uz": "Xodim topilmadi.",
        "ru": "Сотрудник не найден.",
    },
    "Managers only": {
        "uz": "Bu amal faqat menejerlar uchun.",
        "ru": "Доступно только менеджерам.",
    },
    "Forbidden": {
        "uz": "Ushbu amal taqiqlangan.",
        "ru": "Действие запрещено.",
    },
    "refresh_token is required": {
        "uz": "refresh_token kiritilishi shart.",
        "ru": "Требуется передать refresh_token.",
    },
    "Unknown actor type": {
        "uz": "Noma'lum foydalanuvchi turi.",
        "ru": "Неизвестный тип субъекта.",
    },
    "Missing filename": {
        "uz": "Fayl nomi ko'rsatilmagan.",
        "ru": "Имя файла не указано.",
    },
    "Unsupported file type": {
        "uz": "Bu turdagi fayl qo'llab-quvvatlanmaydi.",
        "ru": "Неподдерживаемый тип файла.",
    },
    "Empty file": {
        "uz": "Fayl bo'sh.",
        "ru": "Файл пуст.",
    },
    "File not found": {
        "uz": "Fayl topilmadi.",
        "ru": "Файл не найден.",
    },
    "No fields provided for update": {
        "uz": "Yangilash uchun hech qanday maydon berilmagan.",
        "ru": "Нет данных для обновления.",
    },
    "Invalid credentials": {
        "uz": "Login yoki parol noto'g'ri.",
        "ru": "Неверный логин или пароль.",
    },
    "Old password is incorrect": {
        "uz": "Eski parol noto'g'ri.",
        "ru": "Старый пароль указан неверно.",
    },
    "Staff with this phone already exists": {
        "uz": "Bu telefon raqamiga ega xodim allaqachon mavjud.",
        "ru": "Сотрудник с таким номером уже существует.",
    },
    "Only managers can create staff": {
        "uz": "Xodimlarni faqat menejer yaratishi mumkin.",
        "ru": "Создавать сотрудников может только менеджер.",
    },
    "Only managers can perform this action": {
        "uz": "Bu amalni faqat menejer bajarishi mumkin.",
        "ru": "Это действие доступно только менеджерам.",
    },
    "Only managers can add cashback": {
        "uz": "Keshbekni faqat menejer qo'shishi mumkin.",
        "ru": "Добавлять кэшбэк может только менеджер.",
    },
    "Cashback payment amount must be at least 50,000 UZS.": {
        "uz": "Keshbek bilan to'lash uchun summa kamida 50 000 so'm bo'lishi kerak.",
        "ru": "Сумма оплаты кешбэком должна быть не менее 50 000 сум.",
    },
    "Cashback balance must be at least 50,000 UZS to pay with cashback.": {
        "uz": "Keshbek balansida kamida 50 000 so'm bo'lishi kerak.",
        "ru": "На балансе кешбэка должно быть не менее 50 000 сум.",
    },
    "Insufficient cashback balance.": {
        "uz": "Keshbek balansi yetarli emas.",
        "ru": "Недостаточно средств на балансе кешбэка.",
    },
    "Cashback payment is available.": {
        "uz": "Keshbek bilan to'lovga ruxsat beriladi.",
        "ru": "Оплата кешбэком возможна.",
    },
    "Waiter not found": {
        "uz": "Ofitsiant topilmadi.",
        "ru": "Официант не найден.",
    },
    "Cannot delete waiter with related records": {
        "uz": "Bog'liq yozuvlari mavjud ofitsiantni o'chirib bo'lmaydi.",
        "ru": "Невозможно удалить официанта с связанными записями.",
    },
    "Notification not found": {
        "uz": "Bildirishnoma topilmadi.",
        "ru": "Уведомление не найдено.",
    },
    "News not found": {
        "uz": "Yangilik topilmadi.",
        "ru": "Новость не найдена.",
    },
    "Category not found": {
        "uz": "Kategoriya topilmadi.",
        "ru": "Категория не найдена.",
    },
    "Product not found": {
        "uz": "Mahsulot topilmadi.",
        "ru": "Товар не найден.",
    },
    "Invalid refresh token": {
        "uz": "Yangilash tokeni yaroqsiz.",
        "ru": "Недействительный refresh-токен.",
    },
    "Invalid token actor type": {
        "uz": "Tokenning aktor turi noto'g'ri.",
        "ru": "Неверный тип субъекта в токене.",
    },
    "SMS provider is not configured": {
        "uz": "SMS provayder sozlanmagan.",
        "ru": "SMS-провайдер не настроен.",
    },
    "SMS jo'natib bo'lmadi yoki telefon raqamni noto'g'ri": {
        "uz": "SMS jo'natib bo'lmadi yoki telefon raqam noto'g'ri.",
        "ru": "Не удалось отправить SMS или номер указан неверно.",
    },
    "Invalid OTP code": {
        "uz": "SMS kodi noto'g'ri.",
        "ru": "Неверный SMS-код.",
    },
    "OTP has expired": {
        "uz": "SMS kodining amal qilish muddati tugagan.",
        "ru": "Срок действия SMS-кода истёк.",
    },
    "Invalid waiter referral code": {
        "uz": "Ofitsiantning referal kodi noto'g'ri.",
        "ru": "Неверный реферальный код официанта.",
    },
    "Bu telefon raqamda foydalanuvchu mavjud.": {
        "uz": "Bu telefon raqamda foydalanuvchi mavjud.",
        "ru": "Такой номер телефона уже зарегистрирован.",
    },
    "Bu raqam orqali user yo'q, iltimos akkaunt yaratishni bosing.": {
        "uz": "Bu raqam orqali foydalanuvchi topilmadi, iltimos akkaunt yarating.",
        "ru": "По этому номеру пользователь не найден, пожалуйста, создайте аккаунт.",
    },
    "Bu raqam orqali foydalanuvchi topilmadi, iltimos akkaunt yaratishni bosing.": {
        "uz": "Bu raqam orqali foydalanuvchi topilmadi, iltimos akkaunt yarating.",
        "ru": "По этому номеру пользователь не найден, пожалуйста, создайте аккаунт.",
    },
    "Failed to generate unique referral code": {
        "uz": "Unikal referal kodini yaratib bo'lmadi.",
        "ru": "Не удалось сгенерировать уникальный реферальный код.",
    },
    "Only managers can perform this action": {
        "uz": "Bu amalni faqat menejer bajarishi mumkin.",
        "ru": "Это действие доступно только менеджерам.",
    },
    "Only managers can add cashback": {
        "uz": "Keshbekni faqat menejer qo'shishi mumkin.",
        "ru": "Добавлять кэшбэк может только менеджер.",
    },
}


def _localize_dynamic(message: str) -> dict[str, str] | None:
    match = _RATE_LIMIT_PATTERN.match(message)
    if match:
        minutes = match.group(1)
        return {
            "uz": message,
            "ru": f"Отправлено слишком много запросов, попробуйте снова через {minutes} минут.",
        }
    return None


def localize_message(message: str, *, uz: str | None = None, ru: str | None = None) -> dict[str, str]:
    """
    Convert a raw error message into a bilingual {\"uz\", \"ru\"} payload.
    Unknown messages fall back to the original text for both languages.
    """

    if uz is not None or ru is not None:
        return {
            "uz": uz if uz is not None else (ru or message),
            "ru": ru if ru is not None else (uz or message),
        }

    text = (message or "").strip()
    if not text:
        return {"uz": "", "ru": ""}

    dynamic = _localize_dynamic(text)
    if dynamic:
        return dynamic

    translation = _TRANSLATIONS.get(text)
    if translation:
        return translation

    return {"uz": text, "ru": text}

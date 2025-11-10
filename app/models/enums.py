from enum import Enum, IntEnum


class StaffRole(str, Enum):
    MANAGER = "MANAGER"
    WAITER = "WAITER"


class CashbackSource(str, Enum):
    QR = "QR"
    ORDER = "ORDER"
    MANUAL = "MANUAL"


class AuthActorType(str, Enum):
    CLIENT = "CLIENT"
    STAFF = "STAFF"


class AuthAction(str, Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    OTP_REQUEST = "OTP_REQUEST"
    OTP_VERIFICATION = "OTP_VERIFICATION"
    FAILED_LOGIN = "FAILED_LOGIN"


class SardobaBranch(IntEnum):
    SARDOBA_GEOFIZIKA = 139235
    SARDOBA_GIDIVON = 157757
    SARDOBA_SEVERNIY = 139350
    SARDOBA_MK5 = 139458


class UserLevel(str, Enum):
    SILVER = "SILVER"
    GOLD = "GOLD"
    PREMIUM = "PREMIUM"

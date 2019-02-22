import sys


WIN32 = sys.platform == "win32"

# Python on Windows doesn't expose these constants in os module

EX_CANTCREAT = 73
EX_CONFIG = 78
EX_DATAERR = 65
EX_IOERR = 74
EX_NOHOST = 68
EX_NOINPUT = 66
EX_NOPERM = 77
EX_NOUSER = 67
EX_OK = 0
EX_OSERR = 71
EX_OSFILE = 72
EX_PROTOCOL = 76
EX_SOFTWARE = 70
EX_TEMPFAIL = 75
EX_UNAVAILABLE = 69
EX_USAGE = 64

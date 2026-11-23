import ctypes
import os

libc = ctypes.CDLL("libc.so.6")

class Timex(ctypes.Structure):
    _fields_ = [
        ("modes", ctypes.c_uint),
        ("offset", ctypes.c_long),
        ("freq", ctypes.c_long),
        ("maxerror", ctypes.c_long),
        ("esterror", ctypes.c_long),
        ("status", ctypes.c_int),
        ("constant", ctypes.c_long),
        ("precision", ctypes.c_long),
        ("tolerance", ctypes.c_long),
    ]

t = Timex()
state = libc.adjtimex(ctypes.byref(t))
print("state:", state, "maxerror:", t.maxerror, "esterror:", t.esterror, "status:", hex(t.status))
print("STA_UNSYNC:", bool(t.status & 0x0040))

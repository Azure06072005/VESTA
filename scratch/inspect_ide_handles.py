import ctypes
from ctypes import wintypes
import sys

# Win32 definitions
SYSTEM_HANDLE_INFORMATION = 16
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
STATUS_SUCCESS = 0

ntdll = ctypes.WinDLL("ntdll.dll")
kernel32 = ctypes.WinDLL("kernel32.dll")

class SYSTEM_HANDLE_TABLE_ENTRY_INFO(ctypes.Structure):
    _fields_ = [
        ("UniqueProcessId", wintypes.USHORT),
        ("CreatorBackTraceIndex", wintypes.USHORT),
        ("ObjectTypeIndex", ctypes.c_ubyte),
        ("HandleAttributes", ctypes.c_ubyte),
        ("HandleValue", wintypes.USHORT),
        ("Object", ctypes.c_void_p),
        ("GrantedAccess", wintypes.ULONG),
    ]

# Let's see if we can use a simpler approach: check if another lakehouse has the snapshot data
print("Checking alternative lakehouses...")
import duckdb
for db_name in ['vesta_preprocessed_full.duckdb', 'vesta_preprocessed_quant.duckdb']:
    try:
        con = duckdb.connect(f'd:/VESTA/db/{db_name}', read_only=True)
        print(f"{db_name} schemas:", con.execute("SELECT schema_name FROM information_schema.schemata").fetchall())
        print(f"{db_name} tables:", con.execute("SHOW TABLES").fetchall())
    except Exception as e:
        print(f"Error {db_name}:", e)

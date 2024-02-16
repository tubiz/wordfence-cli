from ctypes import Structure, POINTER, c_char_p, c_int, \
    c_void_p, c_uint, c_ulonglong, byref, CFUNCTYPE
from enum import IntFlag, IntEnum
from typing import Dict, Optional, Callable, Union, Any

from ..library import load_library, LibraryNotAvailableException

from .vectorscan import VectorscanException, \
    VectorscanLibraryNotAvailableException


try:
    hs = load_library('hs')
except LibraryNotAvailableException:
    raise VectorscanLibraryNotAvailableException('Failed to load libhs')


_hs_version = hs.hs_version
_hs_version.argtypes = []
_hs_version.restype = c_char_p
VERSION = _hs_version().decode('ascii')


class _StructHsDatabase(Structure):
    pass


_hs_database_p = POINTER(_StructHsDatabase)


_hs_error = c_int


class _StructHsCompileError(Structure):
    _fields_ = [
            ('message', c_char_p),
            ('expression', c_int)
        ]


_hs_compile_error_p = POINTER(_StructHsCompileError)


class _StructHsPlatformInfo(Structure):
    pass


_hs_platform_info_p = POINTER(_StructHsPlatformInfo)


_hs_compile_multi = hs.hs_compile_multi
_hs_compile_multi.argtypes = [
        POINTER(c_char_p),
        POINTER(c_uint),
        POINTER(c_int),
        c_int,
        c_int,
        _hs_platform_info_p,
        POINTER(_hs_database_p),
        POINTER(_hs_compile_error_p)
    ]
_hs_compile_multi.restype = _hs_error


_hs_free_database = hs.hs_free_database
_hs_free_database.argtypes = [_hs_database_p]
_hs_free_database.restype = None


class _StructHsScratch(Structure):
    pass


_hs_scratch_p = POINTER(_StructHsScratch)


_hs_alloc_scratch = hs.hs_alloc_scratch
_hs_alloc_scratch.argtypes = [_hs_database_p, POINTER(_hs_scratch_p)]
_hs_alloc_scratch.restype = _hs_error


_hs_free_scratch = hs.hs_free_scratch
_hs_free_scratch.argtypes = [_hs_scratch_p]
_hs_free_scratch.restype = None


_match_event_handler = CFUNCTYPE(
        c_int,
        c_uint,
        c_ulonglong,
        c_ulonglong,
        c_uint,
        c_void_p
    )


_hs_scan = hs.hs_scan
_hs_scan.argtypes = [
        _hs_database_p,
        c_char_p,
        c_uint,
        c_uint,
        _hs_scratch_p,
        _match_event_handler,
        c_void_p
    ]
_hs_scan.restype = _hs_error


class VectorscanFlags(IntFlag):
    NONE = 0
    CASELESS = 1
    DOTALL = 2
    MULTILINE = 4
    SINGLEMATCH = 8
    ALLOWEMPTY = 16
    UTF8 = 32
    UCP = 64
    PREFILTER = 128
    LEFTMODE = 256
    COMBINATION = 512
    QUIET = 1024


class VectorscanMode(IntEnum):
    BLOCK = 1
    STREAM = 2
    VECTORED = 4


class VectorscanErrorType(IntEnum):
    SUCCESS = 0
    INVALID = -1
    NOMEM = -2
    SCAN_TERMINATED = -3
    COMPILER_ERROR = -4
    DB_VERSION_ERROR = -5
    DB_MODE_ERROR = -6
    BAD_ALIGN = -8
    BAD_ALLOC = -9
    SCRATCH_IN_USE = -10
    ARCH_ERROR = -11
    INSUFFICIENT_SPACE = -12
    UNKNOWN_ERROR = -13


class VectorscanError(VectorscanException):

    def __init__(self, error: VectorscanErrorType):
        self.error = error


def _assert_success(error: Union[int, _hs_error]):
    try:
        if isinstance(error, _hs_error):
            error = _hs_error.value
        error = VectorscanErrorType(error)
    except ValueError:
        error = VectorscanErrorType.UNKNOWN_ERROR
    if error is not VectorscanErrorType.SUCCESS:
        raise VectorscanError(error)


class VectorscanCompilerError(VectorscanError):

    def __init__(self, message):
        super().__init__(VectorscanErrorType.COMPILER_ERROR)


def _assert_compilation_success(
            error: Union[int, _hs_error],
            compiler_error: _hs_compile_error_p
        ):
    try:
        _assert_success(error)
    except VectorscanError as e:
        if e.error is VectorscanErrorType.COMPILER_ERROR:
            raise VectorscanCompilerError(
                    compiler_error.contents.message.decode('utf-8')
                )
        else:
            raise


class VectorscanDatabase:

    def __init__(self, database: _hs_database_p):
        self._database = database

    def __del__(self) -> None:
        if self._database is not None:
            _hs_free_database(self._database)
            self._database = None


class VectorscanScratch:

    def __init__(self, database: VectorscanDatabase):
        self._scratch = _hs_scratch_p()
        _hs_alloc_scratch(database._database, byref(self._scratch))

    def __del__(self) -> None:
        if self._scratch is not None:
            _hs_free_scratch(self._scratch)
            self._scratch = None


class VectorscanMatch:

    def __init__(
                self,
                identifier: int,
                start: int,
                end: int,
                context
            ):
        self.identifier = identifier
        self.start = start
        self.end = end
        self.context = context


VectorscanMatchCallback = Callable[[VectorscanMatch], bool]


def _wrap_match_callback(callback: VectorscanMatchCallback):
    def wrapped_callback(
                identifier: int,
                start: int,
                end: int,
                _flags: int,
                context
            ) -> int:
        match = VectorscanMatch(
                identifier,
                start,
                end,
                context
            )
        should_terminate = callback(match)
        return 1 if should_terminate else 0
    return wrapped_callback


class VectorscanScanner:

    def __init__(
                self,
                database: VectorscanDatabase,
                scratch: Optional[VectorscanScratch] = None
            ):
        self.database = database
        self.scratch = scratch if scratch is not None \
            else VectorscanScratch(database)

    def scan(
                self,
                data: Union[bytes, str],
                callback: VectorscanMatchCallback,
                context: Optional[Any] = None
            ):
        if isinstance(data, str):
            data = data.encode('utf-8')

        callback = _wrap_match_callback(callback)

        error = _hs_scan(
                self.database._database,
                c_char_p(data),
                c_uint(len(data)),
                c_uint(0),
                self.scratch._scratch,
                _match_event_handler(callback),
                c_void_p()
            )
        _assert_success(error)


def vectorscan_compile(
            patterns: Dict[int, str],
            mode: VectorscanMode = VectorscanMode.BLOCK,
            flags: VectorscanFlags = VectorscanFlags.NONE,
        ) -> VectorscanDatabase:
    database = _hs_database_p()
    compiler_error = _hs_compile_error_p()
    ids = [c_int(id) for id in patterns.keys()]
    ids = (c_int * len(ids))(*ids)
    expressions = [
            c_char_p(expression.encode('utf-8')) for expression
            in patterns.values()
        ]
    expressions = (c_char_p * len(expressions))(*expressions)
    c_flags = (c_uint * len(ids))()
    for i in range(0, len(ids)):
        c_flags[i] = c_uint(flags)
    error = _hs_compile_multi(
            expressions,
            c_flags,
            ids,
            c_int(len(patterns)),
            c_int(mode),
            _hs_platform_info_p(),
            byref(database),
            byref(compiler_error)
        )
    _assert_compilation_success(error, compiler_error)
    return VectorscanDatabase(database)


def vectorscan_test(patterns=None):
    if patterns is None:
        patterns = {
                1: 'Test'
            }
    flags = (
            VectorscanFlags.CASELESS |
            VectorscanFlags.SINGLEMATCH |
            VectorscanFlags.ALLOWEMPTY
        )
    database = vectorscan_compile(
            patterns,
            VectorscanMode.BLOCK,
            flags=flags
        )
    scanner = VectorscanScanner(
            database
        )

    def callback(match: VectorscanMatch) -> bool:
        print(vars(match))

    print('Scan 1')
    scanner.scan('Test', callback)
    print('Scan 2')
    scanner.scan('no match', callback)
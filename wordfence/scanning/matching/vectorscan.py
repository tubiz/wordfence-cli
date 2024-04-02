from typing import Optional

from ...intel.signatures import SignatureSet
from ...logging import log
from ...util import vectorscan

from .matching import MatchEngineOptions, Matcher, BaseMatcherContext, \
        MatchWorkspace, Compiler


if not vectorscan.AVAILABLE:
    raise RuntimeError('Vectorscan is not available')


from ...util.vectorscan import VectorscanStreamScanner, VectorscanMatch, \
        VectorscanFlags, VectorscanDatabase, VectorscanScanTerminated, \
        VectorscanMode, vectorscan_compile, vectorscan_deserialize


class VectorscanMatcherContext(BaseMatcherContext):

    def __init__(self, matcher: Matcher):
        super().__init__(matcher)
        self.matched = None

    def _match_callback(self, match: VectorscanMatch) -> bool:
        self._record_match(
                identifier=match.identifier,
                matched=''
            )
        self.matched = True
        return False if self.matcher.match_all else True

    def process_chunk(
                self,
                chunk: bytes,
                start: bool = False,
                workspace: Optional[MatchWorkspace] = None
            ) -> bool:
        self.matched = False
        try:
            self.matcher.scanner.scan(chunk)
        except VectorscanScanTerminated:
            return True
        return self.matched

    def __enter__(self):
        self.matcher.scanner.set_callback(self._match_callback)
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.matcher.scanner.reset()


class VectorscanCompiler(Compiler):

    def compile(self, signature_set: SignatureSet) -> bytes:
        patterns = {
                signature.identifier: signature.rule
                for signature in signature_set.signatures.values()
            }
        pattern_count = len(patterns)
        log.debug(
                f'Compiling {pattern_count} pattern(s) '
                'to vectorscan database...'
            )
        flags = (
                VectorscanFlags.CASELESS |
                VectorscanFlags.SINGLEMATCH |
                VectorscanFlags.ALLOWEMPTY
            )
        database = vectorscan_compile(
                patterns,
                mode=VectorscanMode.STREAM,
                flags=flags
            )
        log.debug('Successfully compiled vectorscan database')
        return database

    def compile_serializable(self, signature_set: SignatureSet) -> bytes:
        database = self.compile(signature_set)
        return database.serialize()


class VectorscanMatcher(Matcher):

    def __init__(
                self,
                signature_set: SignatureSet,
                match_all: bool = False,
                database_source: Optional[bytes] = None,
                lazy: bool = False
            ):
        self.signature_set = signature_set
        self.match_all = match_all
        self.database_source = database_source
        self.database = None
        self.scanner = None
        super().__init__(
                signature_set=signature_set,
                match_all=match_all,
                lazy=lazy
            )

    def _compile_database(self) -> VectorscanDatabase:
        compiler = VectorscanCompiler()
        return compiler.compile(self.signature_set)

    def _load_database(self, data) -> VectorscanDatabase:
        log.debug('Deserializing pre-compiled vectorscan database...')
        database = vectorscan_deserialize(data)
        log.debug('Successfully deserialized vectorscan database')
        return database

    def _initialize_database(self) -> VectorscanDatabase:
        if self.database_source:
            return self._load_database(self.database_source)
        else:
            return self._compile_database()

    def _prepare(self) -> None:
        log.debug('Preparing vectorscan matcher...')
        self.database = self._initialize_database()
        log.debug('Successfully prepared vectorscan matcher')

    def _prepare_thread(self) -> None:
        log.debug('Preparding thread-specific vectorscan scanner...')
        self.scanner = VectorscanStreamScanner(self.database)
        log.debug('Successfully prepared vectorscan scanner')

    def create_context(self) -> VectorscanMatcherContext:
        return VectorscanMatcherContext(
                self
            )


def create_compiler(options: MatchEngineOptions):
    return VectorscanCompiler()


def create_matcher(options: MatchEngineOptions) -> VectorscanMatcher:
    return VectorscanMatcher(
            options.signature_set,
            match_all=options.match_all,
            database_source=options.database_source,
            lazy=options.lazy
        )

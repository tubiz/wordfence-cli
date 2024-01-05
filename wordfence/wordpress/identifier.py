from enum import Enum
from typing import Optional
from pathlib import Path

from .site import WordpressSite
from .exceptions import WordpressException
from .extension import Extension


class FileType(str, Enum):
    CORE = 'core'
    PLUGIN = 'plugin'
    THEME = 'theme'
    UNKNOWN = 'unknown'


class FileIdentity:

    def __init__(
                self,
                type: FileType,
                site: Optional[WordpressSite] = None,
                extension: Optional[Extension] = None,
            ):
        self.type = type
        self.site = site
        self.extension = extension

    def is_final(self) -> bool:
        return False


class GroupIdentity(FileIdentity):

    def __init__(
                self,
                type: FileType,
                path: Path,
                site: Optional[WordpressSite] = None,
                extension: Optional[Extension] = None,
                final: bool = False
            ):
        super().__init__(type, site, extension)
        self.path = path
        self.final = final

    def is_final(self) -> bool:
        return self.final


class KnownFileIdentity(FileIdentity):

    def __init__(
                self,
                type: FileType,
                local_path: str,
                site: Optional[WordpressSite] = None,
                extension: Optional[Extension] = None,
            ):
        super().__init__(type, site, extension)
        self.local_path = local_path

    def is_final(self) -> bool:
        return True

    def __str__(self) -> str:
        if self.extension is None:
            software = 'WordPress'
            version = self.site.get_version()
        else:
            software = self.extension.get_name()
            version = self.extension.version
        return f'{self.local_path} of {self.type} {software} ({version})'


class KnownPath:

    def __init__(
                self,
                path: Optional[str] = None,
                identity: Optional[FileIdentity] = None
            ):
        self.path = path
        self.identity = identity
        self.children = {}

    def is_root(self) -> bool:
        return self.path is None

    def prepare_path(self, path: Path) -> Path:
        return path.expanduser().resolve()

    def find_identity(self, path: Path) -> type:
        node = self
        path = self.prepare_path(path)
        for component in path.parts:
            if node.identity is not None and node.identity.is_final():
                break
            try:
                node = node.children[component]
            except KeyError:
                break
        return node.identity

    def set_identity(self, path: Path, identity: FileIdentity) -> None:
        node = self
        path = self.prepare_path(path)
        for component in path.parts:
            if component not in node.children:
                node.children[component] = KnownPath()
            node = node.children[component]
        node.identity = identity


class FileIdentifier:

    def __init__(self):
        self.known_paths = KnownPath()

    def _identify_new_path(self, path: Path):
        try:
            site = WordpressSite(str(path), is_child_path=True)
            core_path = Path(site.core_path)
            self.known_paths.set_identity(
                    core_path,
                    GroupIdentity(
                        type=FileType.CORE,
                        path=core_path,
                        site=site
                    )
                )
            for plugin in site.get_all_plugins():
                self.known_paths.set_identity(
                        plugin.path,
                        GroupIdentity(
                            type=FileType.PLUGIN,
                            path=plugin.path,
                            site=site,
                            extension=plugin,
                            final=True
                        )
                    )
            for theme in site.get_themes():
                self.known_paths.set_identity(
                        theme.path,
                        GroupIdentity(
                            type=FileType.THEME,
                            path=theme.path,
                            site=site,
                            extension=theme,
                            final=True
                        )
                    )
        except WordpressException:
            self.known_paths.set_identity(
                    path,
                    FileIdentity(
                        type=FileType.UNKNOWN
                    )
                )

    def identify(self, path: Path, identify_new: bool = True) -> FileIdentity:
        identity = self.known_paths.find_identity(path)
        if identity is None:
            if identify_new:
                self._identify_new_path(path)
                return self.identify(path, False)
            else:
                return FileIdentity(FileType.UNKNOWN)
        elif isinstance(identity, GroupIdentity):
            local_path = path.relative_to(identity.path) \
                    if path != identity.path \
                    else path.name
            identity = KnownFileIdentity(
                    identity.type,
                    local_path,
                    identity.site,
                    identity.extension
                )
            self.known_paths.set_identity(path, identity)
        return identity

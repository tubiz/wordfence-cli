from argparse import ArgumentParser
from types import SimpleNamespace
from typing import Any, Dict, Optional

from .config_items import ConfigItemDefinition


class Config(SimpleNamespace):

    def __init__(
                self,
                definitions,
                parser: ArgumentParser,
                subcommand: Optional[str],
                ini_path: Optional[str] = None
            ):
        super().__init__()
        self._definitions = definitions
        self._parser = parser
        self.subcommand = subcommand
        self.ini_path = ini_path
        self.trailing_arguments = None

    def values(self) -> Dict[str, Any]:
        result: Dict[str, Any] = dict()
        for prop, value in vars(self).items():
            if (prop.startswith('_') or callable(value) or
                    isinstance(value, classmethod)):
                continue
            result[prop] = value
        return result

    def get(self, property_name, default=None) -> Any:
        return getattr(self, property_name, default)

    def define(self, property_name) -> ConfigItemDefinition:
        return self._definitions[property_name]

    def has_ini_file(self) -> bool:
        return self.ini_path is not None

    def display_help(self) -> None:
        self._parser.print_help()
"""
Configuration management for the Trading Data Agent.

Loads configuration from YAML file with environment variable support.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class Config:
    """Configuration loader and accessor."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config YAML file. If None, searches default locations.
        """
        self._config: Dict[str, Any] = {}
        self._config_path = self._resolve_config_path(config_path)
        self._load_config()

    def _resolve_config_path(self, config_path: Optional[str]) -> Path:
        """Resolve the configuration file path."""
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Search default locations
        search_paths = [
            Path("config/config.yaml"),
            Path("config.yaml"),
            Path(__file__).parent.parent / "config" / "config.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return path

        raise FileNotFoundError(
            f"No config file found. Searched: {[str(p) for p in search_paths]}"
        )

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f) or {}

        # Process environment variable overrides
        self._process_env_overrides()

    def _process_env_overrides(self) -> None:
        """Process environment variable overrides."""
        # Allow env vars to override specific settings
        env_mappings = {
            'TRADING_AGENT_LOG_LEVEL': ('general', 'log_level'),
            'TRADING_AGENT_OUTPUT_DIR': ('general', 'output_directory'),
            'TRADING_AGENT_LOG_DIR': ('general', 'log_directory'),
        }

        for env_var, config_path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(config_path, value)

    def _set_nested(self, path: tuple, value: Any) -> None:
        """Set a nested configuration value."""
        current = self._config
        for key in path[:-1]:
            current = current.setdefault(key, {})
        current[path[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a top-level configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._config.get(key, default)

    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """
        Get a nested configuration value.

        Args:
            *keys: Sequence of keys to traverse
            default: Default value if path not found

        Returns:
            Configuration value or default
        """
        current = self._config
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return default
            else:
                return default
        return current

    @property
    def watchlist_stocks(self) -> list:
        """Get the stock watchlist."""
        return self.get_nested('watchlist', 'stocks', default=[])

    @property
    def watchlist_futures(self) -> list:
        """Get the futures watchlist."""
        return self.get_nested('watchlist', 'futures', default=['ES', 'NQ', 'YM'])

    @property
    def output_directory(self) -> Path:
        """Get the output directory path."""
        output_dir = self.get_nested('general', 'output_directory', default='./output')
        return Path(output_dir)

    @property
    def log_directory(self) -> Path:
        """Get the log directory path."""
        log_dir = self.get_nested('general', 'log_directory', default='./logs')
        return Path(log_dir)

    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return self.get_nested('general', 'log_level', default='INFO')

    def is_source_enabled(self, source_name: str) -> bool:
        """Check if a data source is enabled."""
        return self.get_nested('sources', source_name, 'enabled', default=False)

    def get_source_config(self, source_name: str) -> Dict[str, Any]:
        """Get configuration for a specific data source."""
        return self.get_nested('sources', source_name, default={})

    def __repr__(self) -> str:
        return f"Config(path={self._config_path})"

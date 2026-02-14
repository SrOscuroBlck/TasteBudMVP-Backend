import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, List
import yaml

from utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfigurationError(Exception):
    pass


class ConfigLoader:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            base_dir = Path(__file__).resolve().parent
            config_path = base_dir / "config.yaml"
        
        self.config_path = config_path
        self._config: Optional[Dict[str, Any]] = None
        self._last_loaded: Optional[float] = None
    
    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigurationError(f"config file not found: {self.config_path}")
        
        current_mtime = self.config_path.stat().st_mtime
        
        if not force_reload and self._config is not None and self._last_loaded == current_mtime:
            return self._config
        
        logger.info(
            "Loading configuration from file",
            extra={"config_path": str(self.config_path)}
        )
        
        with open(self.config_path, "r") as f:
            raw_config = yaml.safe_load(f)
        
        if raw_config is None:
            raise ConfigurationError("config file is empty")
        
        self._config = self._interpolate_env_vars(raw_config)
        self._last_loaded = current_mtime
        
        logger.info("Configuration loaded successfully")
        
        return self._config
    
    def _interpolate_env_vars(self, config: Any) -> Any:
        if isinstance(config, dict):
            return {
                key: self._interpolate_env_vars(value)
                for key, value in config.items()
            }
        elif isinstance(config, list):
            return [self._interpolate_env_vars(item) for item in config]
        elif isinstance(config, str):
            return self._replace_env_vars_in_string(config)
        else:
            return config
    
    def _replace_env_vars_in_string(self, value: str) -> str:
        pattern = re.compile(r'\$\{([^}]+)\}')
        
        def replacer(match):
            env_var = match.group(1)
            env_value = os.getenv(env_var)
            
            if env_value is None:
                logger.warning(
                    f"Environment variable not found: {env_var}",
                    extra={"env_var": env_var}
                )
                return match.group(0)
            
            return env_value
        
        return pattern.sub(replacer, value)
    
    def get(self, path: str, default: Any = None) -> Any:
        if self._config is None:
            self.load()
        
        keys = path.split('.')
        current = self._config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def reload(self) -> Dict[str, Any]:
        logger.info("Reloading configuration")
        return self.load(force_reload=True)


class ConfigValidator:
    @staticmethod
    def validate_server_config(config: Dict[str, Any]) -> List[str]:
        errors = []
        
        server = config.get('server', {})
        
        port = server.get('port')
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append(f"invalid port: {port}")
        
        return errors
    
    @staticmethod
    def validate_recommendation_config(config: Dict[str, Any]) -> List[str]:
        errors = []
        
        rec = config.get('recommendation', {})
        
        for key in ['lambda_cuisine', 'lambda_pop', 'mmr_alpha', 'exploration_coefficient']:
            value = rec.get(key)
            if value is not None and (not isinstance(value, (int, float)) or value < 0 or value > 1):
                errors.append(f"invalid {key}: {value} (must be between 0 and 1)")
        
        return errors
    
    @staticmethod
    def validate_temporal_decay_config(config: Dict[str, Any]) -> List[str]:
        errors = []
        
        decay = config.get('temporal_decay', {})
        
        feedback_half_life = decay.get('feedback_half_life_days')
        if not isinstance(feedback_half_life, int) or feedback_half_life < 1:
            errors.append(f"invalid feedback_half_life_days: {feedback_half_life}")
        
        return errors
    
    @staticmethod
    def validate_faiss_config(config: Dict[str, Any]) -> List[str]:
        errors = []
        
        faiss = config.get('faiss', {})
        
        dimension = faiss.get('dimension')
        if dimension not in [64, 1536]:
            errors.append(f"invalid FAISS dimension: {dimension} (must be 64 or 1536)")
        
        maintenance = faiss.get('maintenance', {})
        interval_hours = maintenance.get('interval_hours')
        if not isinstance(interval_hours, int) or interval_hours < 1:
            errors.append(f"invalid maintenance interval_hours: {interval_hours}")
        
        return errors
    
    @staticmethod
    def validate(config: Dict[str, Any]) -> List[str]:
        all_errors = []
        
        all_errors.extend(ConfigValidator.validate_server_config(config))
        all_errors.extend(ConfigValidator.validate_recommendation_config(config))
        all_errors.extend(ConfigValidator.validate_temporal_decay_config(config))
        all_errors.extend(ConfigValidator.validate_faiss_config(config))
        
        return all_errors


config_loader: Optional[ConfigLoader] = None


def init_config_loader(config_path: Optional[Path] = None) -> ConfigLoader:
    global config_loader
    config_loader = ConfigLoader(config_path=config_path)
    
    config = config_loader.load()
    
    validation_errors = ConfigValidator.validate(config)
    if validation_errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
        logger.error(error_msg)
        raise ConfigurationError(error_msg)
    
    logger.info("Configuration validated successfully")
    
    return config_loader


def get_config_loader() -> ConfigLoader:
    if config_loader is None:
        raise ConfigurationError("config loader not initialized. Call init_config_loader() first")
    return config_loader

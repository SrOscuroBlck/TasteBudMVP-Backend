#!/usr/bin/env python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import init_config_loader, ConfigValidator
from utils.logger import setup_logger

logger = setup_logger(__name__)


def validate_configuration():
    print("\n" + "="*80)
    print(" TasteBud Configuration Validator")
    print("="*80 + "\n")
    
    try:
        print("[INFO] Loading configuration from config/config.yaml...")
        config_loader = init_config_loader()
        config = config_loader.load()
        
        print("[INFO] Configuration loaded successfully\n")
        
        print("[INFO] Running validation checks...")
        errors = ConfigValidator.validate(config)
        
        if errors:
            print(f"\n[ERROR] Configuration validation failed with {len(errors)} error(s):\n")
            for error in errors:
                print(f"  ❌ {error}")
            print()
            return False
        
        print("[INFO] All validation checks passed ✓\n")
        
        print("Configuration Summary:")
        print("-" * 80)
        print(f"  Server:           {config.get('server', {}).get('host')}:{config.get('server', {}).get('port')}")
        print(f"  Debug Mode:       {config.get('server', {}).get('debug')}")
        print(f"  FAISS Dimension:  {config.get('faiss', {}).get('dimension')}")
        print(f"  Index Maintenance: {config.get('faiss', {}).get('maintenance', {}).get('enabled')}")
        print(f"  Prometheus:       {config.get('observability', {}).get('enable_prometheus')}")
        print(f"  Log Level:        {config.get('observability', {}).get('log_level')}")
        print("-" * 80 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to validate configuration: {str(e)}\n")
        logger.error("Configuration validation failed", exc_info=True)
        return False


if __name__ == "__main__":
    success = validate_configuration()
    sys.exit(0 if success else 1)

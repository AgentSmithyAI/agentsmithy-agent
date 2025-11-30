"""Configuration management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agentsmithy.api.schemas import (
    ConfigMetadata,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigUpdateResponse,
)
from agentsmithy.config.manager import get_config_manager
from agentsmithy.config.schema import (
    ConfigValidationError,
    apply_deletions,
    build_config_metadata,
    deep_merge,
    validate_config,
)
from agentsmithy.utils.logger import api_logger

router = APIRouter()


@router.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get all configuration values.

    Returns the complete configuration dictionary including defaults
    and user-defined values.
    """
    try:
        config_manager = get_config_manager()
        config_dict = config_manager.get_all()
        metadata = ConfigMetadata(**build_config_metadata(config_dict))

        api_logger.info("Configuration retrieved", num_keys=len(config_dict))
        return ConfigResponse(config=config_dict, metadata=metadata)
    except HTTPException:
        raise
    except RuntimeError as e:
        api_logger.error("Config manager not initialized", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Configuration manager not initialized",
        ) from e
    except Exception as e:
        api_logger.error(
            "Failed to retrieve configuration", error=str(e), exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve configuration: {str(e)}",
        ) from e


@router.put("/api/config", response_model=ConfigUpdateResponse)
async def update_config(request: ConfigUpdateRequest):
    """Update configuration values.

    Updates the configuration with the provided key-value pairs.
    The changes are persisted to the configuration file.

    Args:
        request: Configuration update request with config dictionary

    Returns:
        Success status, message, and updated configuration
    """
    try:
        config_manager = get_config_manager()

        current_config = config_manager.get_all()
        # First merge, then apply explicit null deletions
        merged_config = deep_merge(current_config, request.config)
        merged_config = apply_deletions(merged_config, request.config)
        try:
            validate_config(merged_config)
        except ConfigValidationError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Invalid configuration",
                    "errors": e.errors,
                },
            ) from e

        # Pass both updates and deletions to manager
        await config_manager.update_with_deletions(request.config)

        updated_config = config_manager.get_all()
        metadata = ConfigMetadata(**build_config_metadata(updated_config))

        api_logger.info(
            "Configuration updated",
            num_keys_updated=len(request.config),
            keys=list(request.config.keys()),
        )

        return ConfigUpdateResponse(
            success=True,
            message=f"Successfully updated {len(request.config)} configuration key(s)",
            config=updated_config,
            metadata=metadata,
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        api_logger.error("Config manager not initialized", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Configuration manager not initialized",
        ) from e
    except Exception as e:
        api_logger.error(
            "Failed to update configuration",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update configuration: {str(e)}",
        ) from e

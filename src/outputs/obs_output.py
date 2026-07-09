from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from core import config
from outputs.base_output import BaseOutput

logger = logging.getLogger(__name__)

try:
    import obsws_python as obs

    OBS_AVAILABLE = True
except ImportError:
    obs = None
    OBS_AVAILABLE = False
    logger.warning("obsws_python not installed — OBS output disabled. Run: pip install obsws-python")


COLOR_CORRECTION_FILTER_KIND = "color_filter"
DEFAULT_COLOR_CORRECTION_FILTER_NAME = "Opacity"


@dataclass(frozen=True)
class ObsConnectionSettings:
    host: str
    port: int
    password: str
    timeout: float = 3.0


class OBSOutput(BaseOutput):
    """
    Thin service wrapper around obs-websocket.

    The class is intentionally structured around a few reusable primitives:
    - scene control
    - source visibility / text updates
    - source filter management
    - filter-specific helpers like opacity

    That keeps the class extensible as more OBS automation is added.
    """

    def __init__(self, connection: ObsConnectionSettings | None = None):
        super().__init__("obs_output")
        self._connection = connection
        self._client = None

    def _resolve_connection(self) -> ObsConnectionSettings:
        if self._connection is not None:
            return self._connection

        return ObsConnectionSettings(
            host=config.get("obs.host", "localhost"),
            port=int(config.get("obs.port", 4455)),
            password=config.get("obs.password", ""),
            timeout=float(config.get("obs.timeout", 3.0)),
        )

    def _has_client(self) -> bool:
        return self._client is not None

    def _log_unavailable(self, action: str):
        logger.warning("OBSOutput: cannot %s because no OBS client is connected.", action)

    def _source_args(
        self,
        *,
        source_name: str | None = None,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if canvas_uuid is not None:
            args["canvasUuid"] = canvas_uuid
        if source_name is not None:
            args["sourceName"] = source_name
        if source_uuid is not None:
            args["sourceUuid"] = source_uuid
        return args

    def _response_value(self, response: Any, key: str, default: Any = None) -> Any:
        if response is None:
            return default
        if isinstance(response, Mapping):
            return response.get(key, default)
        return getattr(response, key, default)

    def _request(self, method_name: str, *args, **kwargs) -> Any:
        if not self._has_client():
            self._log_unavailable(method_name)
            return None

        method = getattr(self._client, method_name, None)
        if method is None:
            logger.error("OBSOutput: client does not expose '%s'.", method_name)
            return None

        try:
            return method(*args, **kwargs)
        except Exception as exc:
            logger.error("OBSOutput %s failed: %s", method_name, exc)
            return None

    def setup(self):
        if not OBS_AVAILABLE:
            logger.warning("OBSOutput: obsws_python unavailable.")
            return

        settings = self._resolve_connection()
        try:
            self._client = obs.ReqClient(
                host=settings.host,
                port=settings.port,
                password=settings.password,
                timeout=settings.timeout,
            )
            logger.info("OBS connected at %s:%s", settings.host, settings.port)
        except Exception as exc:
            self._client = None
            logger.error("OBS connection failed: %s", exc)

    def teardown(self):
        if self._client:
            try:
                disconnect = getattr(self._client, "disconnect", None)
                if disconnect is not None:
                    disconnect()
            except Exception:
                pass
        self._client = None

    # ---------------------------------------------------------------------
    # Scene / source helpers
    # ---------------------------------------------------------------------

    def switch_scene(self, scene_name: str):
        self._request("set_current_program_scene", scene_name=scene_name)

    def set_source_visible(self, scene: str, source: str, visible: bool):
        response = self._request("get_scene_item_id", scene_name=scene, source_name=source)
        item_id = self._response_value(response, "sceneItemId")
        if item_id is None:
            return

        self._request("set_scene_item_enabled", scene_name=scene, scene_item_id=item_id, scene_item_enabled=visible)

    def update_text(self, source_name: str, text: str):
        """Update a Text (GDI+ or FreeType 2) source's content."""
        self._request("set_input_settings", input_name=source_name, input_settings={"text": text}, overlay=True)

    def trigger_media(self, source_name: str):
        """Restart a media source (e.g. play a video clip)."""
        self._request(
            "trigger_media_input_action",
            input_name=source_name,
            media_action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
        )

    # ---------------------------------------------------------------------
    # Generic filter helpers
    # ---------------------------------------------------------------------

    def get_source_filter(
        self,
        source_name: str,
        filter_name: str,
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ) -> Any:
        return self._request(
            "get_source_filter",
            filter_name=filter_name,
            **self._source_args(source_name=source_name, source_uuid=source_uuid, canvas_uuid=canvas_uuid),
        )

    def get_source_filter_settings(
        self,
        source_name: str,
        filter_name: str,
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ) -> dict[str, Any] | None:
        response = self.get_source_filter(
            source_name,
            filter_name,
            source_uuid=source_uuid,
            canvas_uuid=canvas_uuid,
        )
        if response is None:
            return None
        settings = self._response_value(response, "filterSettings")
        return dict(settings) if isinstance(settings, Mapping) else settings

    def set_source_filter_settings(
        self,
        source_name: str,
        filter_name: str,
        settings: Mapping[str, Any],
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
        overlay: bool = True,
    ):
        self._request(
            "set_source_filter_settings",
            filter_name=filter_name,
            filter_settings=dict(settings),
            overlay=overlay,
            **self._source_args(source_name=source_name, source_uuid=source_uuid, canvas_uuid=canvas_uuid),
        )

    def set_source_filter_enabled(
        self,
        source_name: str,
        filter_name: str,
        enabled: bool,
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        self._request(
            "set_source_filter_enabled",
            filter_name=filter_name,
            filter_enabled=enabled,
            **self._source_args(source_name=source_name, source_uuid=source_uuid, canvas_uuid=canvas_uuid),
        )

    def create_source_filter(
        self,
        source_name: str,
        filter_name: str,
        filter_kind: str,
        settings: Mapping[str, Any] | None = None,
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        payload = {
            "filter_name": filter_name,
            "filter_kind": filter_kind,
            **self._source_args(source_name=source_name, source_uuid=source_uuid, canvas_uuid=canvas_uuid),
        }
        if settings is not None:
            payload["filter_settings"] = dict(settings)
        self._request("create_source_filter", **payload)

    def ensure_source_filter(
        self,
        source_name: str,
        filter_name: str,
        filter_kind: str,
        settings: Mapping[str, Any] | None = None,
        *,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        existing = self.get_source_filter(
            source_name,
            filter_name,
            source_uuid=source_uuid,
            canvas_uuid=canvas_uuid,
        )

        if existing is None:
            self.create_source_filter(
                source_name,
                filter_name,
                filter_kind,
                settings,
                source_uuid=source_uuid,
                canvas_uuid=canvas_uuid,
            )
            return

        existing_kind = self._response_value(existing, "filterKind")
        if existing_kind is not None and existing_kind != filter_kind:
            logger.warning(
                "OBSOutput: filter '%s' on source '%s' exists as '%s' instead of '%s'. Updating its settings only.",
                filter_name,
                source_name,
                existing_kind,
                filter_kind,
            )

        if settings:
            self.set_source_filter_settings(
                source_name,
                filter_name,
                settings,
                source_uuid=source_uuid,
                canvas_uuid=canvas_uuid,
            )

    def set_filter_enabled(self, source: str, filter_name: str, enabled: bool):
        """Backward-compatible wrapper around set_source_filter_enabled."""
        self.set_source_filter_enabled(source, filter_name, enabled)

    def set_filter_settings(self, source: str, filter_name: str, settings: Mapping[str, Any]):
        """Backward-compatible wrapper around set_source_filter_settings."""
        self.set_source_filter_settings(source, filter_name, settings)

    def set_filter_opacity(
        self,
        source_name: str,
        opacity: float,
        *,
        filter_name: str = DEFAULT_COLOR_CORRECTION_FILTER_NAME,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        """
        Set a source's opacity through OBS's Color Correction filter.

        OBS exposes opacity as a built-in color-correction property where
        0.0 is fully transparent and 1.0 is fully opaque.
        """
        clamped_opacity = max(0.0, min(1.0, float(opacity)))
        self.ensure_source_filter(
            source_name,
            filter_name,
            COLOR_CORRECTION_FILTER_KIND,
            {"opacity": clamped_opacity},
            source_uuid=source_uuid,
            canvas_uuid=canvas_uuid,
        )

    def set_source_opacity(
        self,
        source_name: str,
        opacity: float,
        *,
        filter_name: str = DEFAULT_COLOR_CORRECTION_FILTER_NAME,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        """Preferred convenience API for source opacity."""
        self.set_filter_opacity(
            source_name,
            opacity,
            filter_name=filter_name,
            source_uuid=source_uuid,
            canvas_uuid=canvas_uuid,
        )

    def set_source_opacity_percent(
        self,
        source_name: str,
        opacity_percent: float,
        *,
        filter_name: str = DEFAULT_COLOR_CORRECTION_FILTER_NAME,
        source_uuid: str | None = None,
        canvas_uuid: str | None = None,
    ):
        """Convenience API for callers thinking in percentages instead of 0.0-1.0."""
        self.set_source_opacity(
            source_name,
            float(opacity_percent) / 100.0,
            filter_name=filter_name,
            source_uuid=source_uuid,
            canvas_uuid=canvas_uuid,
        )

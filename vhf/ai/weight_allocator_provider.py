from __future__ import annotations

import importlib
import inspect
import os
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from vhf.logging.log import logger
from vhf.models.allocation import AIProviderMode


ENV_AI_PROVIDER_MODE = "AI_ALLOCATOR_MODE"
ENV_AI_REMOTE_URL = "AI_ALLOCATOR_URL"
ENV_AI_REMOTE_API_KEY = "AI_ALLOCATOR_API_KEY"
ENV_AI_LOCAL_MODULE = "AI_ALLOCATOR_LOCAL_MODULE"
ENV_AI_LOCAL_FUNCTION = "AI_ALLOCATOR_LOCAL_FUNCTION"

DEFAULT_AI_LOCAL_MODULE = "vhf.ai.ai_weight_allocator"
DEFAULT_AI_LOCAL_FUNCTION = "allocate_weights"
DEFAULT_REMOTE_REQUEST_TIMEOUT_SECONDS = 10.0

ALLOWED_PROVIDER_MODES = {mode.value for mode in AIProviderMode}


class WeightAllocatorProviderError(RuntimeError):
    pass


class WeightAllocatorProvider(Protocol):
    name: str

    def allocate(self, context: dict[str, Any], *, timeout_seconds: float) -> Any: ...


class DisabledWeightAllocatorProvider:
    name = "disabled"

    def allocate(self, context: dict[str, Any], *, timeout_seconds: float) -> Any:
        raise WeightAllocatorProviderError("AI allocator is disabled by configuration.")


@dataclass
class LocalWeightAllocatorProvider:
    module_path: str
    function_name: str

    @property
    def name(self) -> str:
        return f"local:{self.module_path}.{self.function_name}"

    def allocate(self, context: dict[str, Any], *, timeout_seconds: float) -> Any:
        try:
            module = importlib.import_module(self.module_path)
        except Exception as exc:
            raise WeightAllocatorProviderError(
                f"Failed to import local allocator module '{self.module_path}': {exc}"
            ) from exc

        fn = getattr(module, self.function_name, None)
        if not callable(fn):
            raise WeightAllocatorProviderError(
                f"Local allocator function '{self.function_name}' was not found/callable in '{self.module_path}'."
            )

        try:
            signature = inspect.signature(fn)
            if len(signature.parameters) == 1:
                return fn(context)
            # Allow future local implementations to accept keyword args.
            return fn(context=context)
        except Exception as exc:
            raise WeightAllocatorProviderError(f"Local allocator execution failed: {exc}") from exc


@dataclass
class RemoteWeightAllocatorProvider:
    url: str
    api_key: str | None = None

    @property
    def name(self) -> str:
        return f"remote:{self.url}"

    def allocate(self, context: dict[str, Any], *, timeout_seconds: float) -> Any:
        if not self.url.startswith("https://"):
            logger.warning(
                "Remote AI allocator URL does not use HTTPS (%s). "
                "API key and context data will be transmitted unencrypted.",
                self.url,
            )

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        effective_timeout = timeout_seconds if timeout_seconds > 0 else DEFAULT_REMOTE_REQUEST_TIMEOUT_SECONDS
        if timeout_seconds <= 0:
            logger.warning(
                "Invalid timeout_seconds=%s for remote AI provider; using default %ss.",
                timeout_seconds,
                DEFAULT_REMOTE_REQUEST_TIMEOUT_SECONDS,
            )

        try:
            response = requests.post(
                self.url,
                json=context,
                headers=headers,
                timeout=effective_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WeightAllocatorProviderError(f"Remote allocator request failed: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise WeightAllocatorProviderError("Remote allocator returned non-JSON response.") from exc


def _resolve_mode(requested_mode: AIProviderMode | None) -> AIProviderMode:
    if requested_mode is not None:
        return requested_mode

    raw_mode = os.getenv(ENV_AI_PROVIDER_MODE, AIProviderMode.auto.value).strip().lower()
    if raw_mode not in ALLOWED_PROVIDER_MODES:
        logger.warning(
            "Unknown AI_ALLOCATOR_MODE '%s'; falling back to auto.", raw_mode
        )
        return AIProviderMode.auto
    return AIProviderMode(raw_mode)


def _build_local_provider() -> LocalWeightAllocatorProvider:
    module_path = os.getenv(ENV_AI_LOCAL_MODULE, DEFAULT_AI_LOCAL_MODULE)
    function_name = os.getenv(ENV_AI_LOCAL_FUNCTION, DEFAULT_AI_LOCAL_FUNCTION)
    return LocalWeightAllocatorProvider(module_path=module_path, function_name=function_name)


def _build_remote_provider() -> RemoteWeightAllocatorProvider:
    url = os.getenv(ENV_AI_REMOTE_URL, "").strip()
    if not url:
        raise WeightAllocatorProviderError(
            "AI_ALLOCATOR_URL is required for remote AI provider mode."
        )
    return RemoteWeightAllocatorProvider(url=url, api_key=os.getenv(ENV_AI_REMOTE_API_KEY))


def resolve_allocator_provider(
    requested_mode: AIProviderMode | None,
) -> tuple[AIProviderMode, WeightAllocatorProvider]:
    mode = _resolve_mode(requested_mode)

    if mode == AIProviderMode.disabled:
        return mode, DisabledWeightAllocatorProvider()

    if mode == AIProviderMode.local:
        return mode, _build_local_provider()

    if mode == AIProviderMode.remote:
        return mode, _build_remote_provider()

    # auto mode: prefer local first (same process), then fallback to remote if configured.
    local_provider = _build_local_provider()
    try:
        # Lightweight sanity check so we fail fast if local provider is not importable.
        importlib.import_module(local_provider.module_path)
        return AIProviderMode.local, local_provider
    except Exception as exc:
        logger.warning(
            "Auto mode: local AI provider not available (%s); trying remote.", exc
        )

    try:
        remote_provider = _build_remote_provider()
        return AIProviderMode.remote, remote_provider
    except WeightAllocatorProviderError as exc:
        logger.warning(
            "Auto mode: remote AI provider not available (%s); AI allocator disabled.", exc
        )
        return AIProviderMode.disabled, DisabledWeightAllocatorProvider()

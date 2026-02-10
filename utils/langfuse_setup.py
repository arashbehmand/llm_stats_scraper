import inspect
import logging
import os
from functools import lru_cache


def _to_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _append_callback(target, callback_name):
    if target is None:
        return [callback_name]
    if isinstance(target, str):
        return [target, callback_name] if target != callback_name else [target]
    if isinstance(target, list):
        if callback_name not in target:
            target.append(callback_name)
        return target
    return target


@lru_cache(maxsize=1)
def initialize_langfuse():
    """
    Optionally enables Langfuse tracing for LiteLLM calls.

    Activation rules:
    - LANGFUSE_ENABLED=true, OR
    - LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are both set
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    explicit_enabled = _to_bool(os.getenv("LANGFUSE_ENABLED", "false"))
    enabled = explicit_enabled or (public_key and secret_key)

    if not enabled:
        return None

    if not public_key or not secret_key:
        logging.warning(
            "Langfuse: enabled but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are missing."
        )
        return None

    try:
        import litellm
        from langfuse import Langfuse
    except Exception as exc:
        logging.warning(f"Langfuse: dependency import failed: {exc}")
        return None

    # LiteLLM 1.81.x passes sdk_integration to Langfuse().
    # If installed langfuse does not accept it (e.g. incompatible major),
    # skip enabling callbacks to avoid breaking report generation.
    try:
        signature = inspect.signature(Langfuse.__init__)
        if "sdk_integration" not in signature.parameters:
            logging.warning(
                "Langfuse: incompatible langfuse package for current LiteLLM "
                "(missing sdk_integration in Langfuse.__init__). "
                "Disable Langfuse or install langfuse<3."
            )
            return None
    except Exception as exc:
        logging.warning(f"Langfuse: failed to inspect client signature: {exc}")
        return None

    # LiteLLM's Langfuse integration reads credentials from env vars.
    # Keep host optional; Langfuse Cloud default is used if not provided.
    if os.getenv("LANGFUSE_HOST"):
        os.environ["LANGFUSE_HOST"] = os.getenv("LANGFUSE_HOST")
    os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
    os.environ["LANGFUSE_SECRET_KEY"] = secret_key

    litellm.callbacks = _append_callback(
        getattr(litellm, "callbacks", None), "langfuse"
    )
    litellm.success_callback = _append_callback(
        getattr(litellm, "success_callback", None), "langfuse"
    )
    litellm.failure_callback = _append_callback(
        getattr(litellm, "failure_callback", None), "langfuse"
    )

    logging.info("Langfuse: tracing enabled for LiteLLM calls.")
    return Langfuse()

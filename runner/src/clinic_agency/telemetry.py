from opentelemetry import trace


def current_trace_id() -> str:
    """Return the active OTel/Langfuse trace ID without logging on an empty context."""
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else ""

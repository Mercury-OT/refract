"""In-memory span store for the reference demo application."""
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

STORE: dict[str, list[dict]] = {}


def reset() -> None:
    """Clear all recorded spans."""
    STORE.clear()


class InMemorySpanExporter(SpanExporter):
    """Append finished spans into `STORE` under their trace id."""

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            trace_id = format(span.context.trace_id, "032x")
            entry = {
                "name": span.name,
                "attributes": dict(span.attributes or {}),
            }
            STORE.setdefault(trace_id, []).append(entry)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

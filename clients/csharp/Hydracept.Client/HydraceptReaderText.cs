using System.Globalization;
using System.Runtime.CompilerServices;
using System.Text.Json;

namespace Hydracept.Client;

/// <summary>
/// Reads partial text from a durable job while that job is still running.
/// Concatenate <see cref="HydraceptReaderTextEvent.Text"/> in sequence order.
/// That text is not the sealed result. Pass the last <see cref="HydraceptReaderTextEvent.Cursor"/>
/// to resume: it is an exclusive lower bound, and an event at or below it is ignored.
/// </summary>
public static class HydraceptReaderText
{
    public const string EventType = "job.reader_text";

    public static async IAsyncEnumerable<HydraceptReaderTextEvent> ReadAsync(
        IHydraceptClient client,
        string jobId,
        string? cursor = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var sawTerminal = false;
        while (!cancellationToken.IsCancellationRequested)
        {
            var cursorAtStart = cursor;
            var page = await client.GetJobEventsAsync(jobId, EventType, cursor, cancellationToken)
                .ConfigureAwait(false);
            if (page.TryGetProperty("events", out var events) && events.ValueKind == JsonValueKind.Array)
            {
                foreach (var evt in events.EnumerateArray())
                {
                    var eventCursor = ReadCursor(evt, "cursor");
                    if (eventCursor == null || !IsAfter(cursor, eventCursor) || !seen.Add(eventCursor))
                        continue;
                    if (!evt.TryGetProperty("payload", out var payload)
                        || !payload.TryGetProperty("text", out var textEl)
                        || textEl.ValueKind != JsonValueKind.String)
                        continue;
                    var text = textEl.GetString();
                    if (string.IsNullOrEmpty(text))
                        continue;
                    var sequence = payload.TryGetProperty("sequence", out var sequenceEl)
                        && sequenceEl.TryGetInt32(out var parsed)
                        ? parsed
                        : 0;
                    var boundary = payload.TryGetProperty("boundary", out var boundaryEl)
                        && boundaryEl.ValueKind == JsonValueKind.String
                        ? boundaryEl.GetString() ?? ""
                        : "";
                    cursor = eventCursor;
                    yield return new HydraceptReaderTextEvent(eventCursor, sequence, text, boundary);
                }
            }

            var nextCursor = page.TryGetProperty("nextCursor", out var next) ? ReadJsonCursor(next) : null;
            if (!string.IsNullOrWhiteSpace(nextCursor) && IsAfter(cursorAtStart, nextCursor))
            {
                cursor = nextCursor;
                continue;
            }

            var job = await client.GetJobAsync(jobId, cancellationToken).ConfigureAwait(false);
            var status = job.TryGetProperty("status", out var statusEl) ? statusEl.GetString() : null;
            if (status is "succeeded" or "failed" or "canceled" or "cancelled")
            {
                // The closing span can land in the same moment as the terminal
                // status. Read the event page once more before stopping.
                if (!sawTerminal)
                {
                    sawTerminal = true;
                    continue;
                }
                yield break;
            }
            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken).ConfigureAwait(false);
        }
    }

    private static string? ReadCursor(JsonElement evt, string name)
    {
        return evt.TryGetProperty(name, out var element) ? ReadJsonCursor(element) : null;
    }

    private static string? ReadJsonCursor(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.String)
            return element.GetString();
        if (element.ValueKind == JsonValueKind.Number && element.TryGetInt64(out var number))
            return number.ToString(CultureInfo.InvariantCulture);
        return null;
    }

    private static bool IsAfter(string? persisted, string candidate)
    {
        if (string.IsNullOrEmpty(persisted))
            return true;
        if (long.TryParse(persisted, NumberStyles.Integer, CultureInfo.InvariantCulture, out var previous)
            && long.TryParse(candidate, NumberStyles.Integer, CultureInfo.InvariantCulture, out var next))
            return next > previous;
        return !string.Equals(persisted, candidate, StringComparison.Ordinal);
    }
}

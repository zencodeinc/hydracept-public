using System.Runtime.CompilerServices;
using System.Text.Json;

namespace Hydracept.Client;

internal static class HydraceptSseReader
{
    public static async IAsyncEnumerable<HydraceptSseEvent> ReadAsync(
        Stream stream,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var reader = new StreamReader(stream);
        string? eventName = null;
        string? eventId = null;
        var dataLines = new List<string>();

        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var line = await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null)
                break;

            if (line.Length == 0)
            {
                if (dataLines.Count > 0)
                {
                    var payload = string.Join("\n", dataLines);
                    using var document = JsonDocument.Parse(payload);
                    yield return new HydraceptSseEvent(eventName ?? "message", document.RootElement.Clone(), eventId);
                }

                eventName = null;
                eventId = null;
                dataLines.Clear();
                continue;
            }

            if (line.StartsWith(':'))
                continue;
            if (line.StartsWith("id:", StringComparison.OrdinalIgnoreCase))
                eventId = line["id:".Length..].Trim();
            else if (line.StartsWith("event:", StringComparison.OrdinalIgnoreCase))
                eventName = line["event:".Length..].Trim();
            else if (line.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
                dataLines.Add(line["data:".Length..].TrimStart());
        }
    }
}

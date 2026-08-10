using System.Text.Json;

namespace Hydracept.Client;

public sealed class HydraceptSseEvent
{
    public HydraceptSseEvent(string eventName, JsonElement data, string? id = null)
    {
        Event = eventName;
        Data = data;
        Id = id;
    }

    public string? Id { get; }

    public string Event { get; }

    public JsonElement Data { get; }
}

namespace Hydracept.Client;

/// <summary>
/// One <c>job.reader_text</c> span. <see cref="Cursor"/> is the replay identity.
/// Persist it with the caller's own job state. The same cursor is the same event.
/// </summary>
public readonly record struct HydraceptReaderTextEvent(
    string Cursor,
    int Sequence,
    string Text,
    string Boundary);

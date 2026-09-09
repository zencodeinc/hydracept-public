namespace Hydracept.Client;

public sealed class HydraceptApiException : Exception
{
    public HydraceptApiException(
        string message,
        int statusCode,
        string? responseBody = null,
        string? errorCode = null,
        string? executionId = null,
        string? receiptId = null)
        : base(message)
    {
        StatusCode = statusCode;
        ResponseBody = responseBody;
        ErrorCode = errorCode;
        ExecutionId = executionId;
        ReceiptId = receiptId;
    }

    public int StatusCode { get; }

    public string? ResponseBody { get; }

    public string? ErrorCode { get; }

    public string? ExecutionId { get; }

    public string? ReceiptId { get; }
}

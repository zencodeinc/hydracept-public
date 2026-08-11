using System;

namespace Hydracept.Unity.Editor.Api
{
    public sealed class HydraceptApiException : Exception
    {
        public int StatusCode { get; }
        public string? ErrorCode { get; }

        public HydraceptApiException(string message, int statusCode, string? errorCode = null)
            : base(message)
        {
            StatusCode = statusCode;
            ErrorCode = errorCode;
        }
    }
}

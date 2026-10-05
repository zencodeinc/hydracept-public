using System.Net;

namespace Hydracept.Client;

public static class HydraceptHttpRetry
{
    private static readonly HashSet<HttpStatusCode> Retryable = new()
    {
        HttpStatusCode.RequestTimeout,
        (HttpStatusCode)429,
        HttpStatusCode.InternalServerError,
        HttpStatusCode.BadGateway,
        HttpStatusCode.ServiceUnavailable,
        HttpStatusCode.GatewayTimeout,
    };

    public static bool IsRetryable(HttpStatusCode status) => Retryable.Contains(status);

    internal static async Task<(HttpStatusCode StatusCode, string BodyText)> SendWithRetryAsync(
        Func<Task<HttpResponseMessage>> send,
        int maxAttempts = 5,
        CancellationToken cancellationToken = default)
    {
        HttpResponseMessage? last = null;
        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                last = await send().ConfigureAwait(false);
            }
            catch (HttpRequestException) when (attempt < maxAttempts)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
                continue;
            }
            catch (TaskCanceledException) when (attempt < maxAttempts && !cancellationToken.IsCancellationRequested)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
                continue;
            }
            catch (TimeoutException) when (attempt < maxAttempts)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
                continue;
            }

            if (last.IsSuccessStatusCode || !IsRetryable(last.StatusCode) || attempt >= maxAttempts)
            {
                var text = await last.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                return (last.StatusCode, text);
            }

            last.Dispose();
            await Task.Delay(TimeSpan.FromMilliseconds(500 * attempt), cancellationToken).ConfigureAwait(false);
        }

        throw new InvalidOperationException("Retry loop exited without a response.");
    }
}

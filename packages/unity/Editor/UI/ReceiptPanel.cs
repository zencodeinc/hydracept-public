using System;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Newtonsoft.Json;
using UnityEditor;
using UnityEngine.UIElements;

namespace Hydracept.Unity.Editor.UI
{
    public static class ReceiptPanel
    {
        public static void Render(VisualElement root, HydraceptJob job, HydraceptReceipt? receipt)
        {
            root.Add(new Label("Receipt"));
            root.Add(new Label($"Capability: {job.CapabilityKey}"));
            if (receipt != null)
            {
                root.Add(new Label($"Receipt ID: {receipt.ReceiptId}"));
                if (receipt.ActualCost.HasValue)
                {
                    root.Add(new Label($"Cost: {receipt.ActualCost:F4} {receipt.Currency ?? "USD"}"));
                }
            }

            root.Add(new Label($"Artifacts: {job.Artifacts.Count}"));

            var copyId = new Button(() => EditorGUIUtility.systemCopyBuffer = receipt?.ReceiptId ?? job.ReceiptId ?? job.JobId)
            {
                text = "Copy Receipt ID",
            };
            var copyJson = new Button(() =>
            {
                var payload = receipt != null
                    ? JsonConvert.SerializeObject(receipt, Formatting.Indented)
                    : JsonConvert.SerializeObject(job, Formatting.Indented);
                EditorGUIUtility.systemCopyBuffer = payload;
            })
            {
                text = "Copy JSON",
            };
            root.Add(copyId);
            root.Add(copyJson);
        }
    }
}

using Hydracept.Unity.Editor.Auth;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.UI
{
    public static class HydraceptMenus
    {
        [MenuItem("Hydracept/Open Window")]
        public static void OpenWindow() => HydraceptWindow.ShowWindow();

        [MenuItem("Hydracept/Refresh Status")]
        public static void RefreshStatus()
        {
            var window = EditorWindow.GetWindow<HydraceptWindow>(false, null, false);
            window.RefreshStatus();
        }

        [MenuItem("Hydracept/Open Generated Assets")]
        public static void OpenGeneratedAssets()
        {
            var path = "Assets/Generated/Hydracept";
            if (!AssetDatabase.IsValidFolder(path))
            {
                Debug.LogWarning("Generated Hydracept folder does not exist yet.");
                return;
            }

            var obj = AssetDatabase.LoadAssetAtPath<Object>(path);
            Selection.activeObject = obj;
            EditorGUIUtility.PingObject(obj);
        }
    }
}

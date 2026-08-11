using System.IO;
using UnityEngine;

namespace Hydracept.Unity.Editor.Auth
{
    public static class WorkspaceLocator
    {
        public static string? FindProjectRoot()
        {
            var dataPath = Application.dataPath;
            if (string.IsNullOrWhiteSpace(dataPath))
            {
                return null;
            }

            var current = new DirectoryInfo(dataPath);
            while (current != null)
            {
                var hydraceptDir = Path.Combine(current.FullName, ".hydracept");
                var assetsDir = Path.Combine(current.FullName, "Assets");
                var projectSettings = Path.Combine(current.FullName, "ProjectSettings");
                if (Directory.Exists(hydraceptDir) || (Directory.Exists(assetsDir) && Directory.Exists(projectSettings)))
                {
                    return current.FullName;
                }

                current = current.Parent;
            }

            return new DirectoryInfo(dataPath).Parent?.FullName;
        }
    }
}

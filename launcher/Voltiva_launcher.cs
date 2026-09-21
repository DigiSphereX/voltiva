// Voltiva launcher — starts the Python desktop app without a console window.
// Compiled with the .NET Framework csc (no extra runtime install).
//     csc /target:winexe /win32icon:energy.ico /r:System.Windows.Forms.dll Voltiva_launcher.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace VoltivaLauncher
{
    internal static class Program
    {
        private const string MissingPython =
            "Voltiva could not find Python (pythonw.exe).\r\n" +
            "Install Python 3.12 64-bit from python.org, then try again.";

        [STAThread]
        private static int Main()
        {
            string dir = AppDomain.CurrentDomain.BaseDirectory;
            string runPy = Path.Combine(dir, "run.py");
            if (!File.Exists(runPy))
            {
                MessageBox.Show("Voltiva could not find run.py next to Voltiva.exe.",
                    "Voltiva", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            string pythonw = FindPythonw();
            if (pythonw == null)
            {
                MessageBox.Show(MissingPython, "Voltiva", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = pythonw,
                    Arguments = "\"" + runPy + "\"",
                    WorkingDirectory = dir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process.Start(psi);
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show("Voltiva could not start.\r\n" + ex.Message,
                    "Voltiva", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static string FindPythonw()
        {
            // 1) pythonw on PATH
            string pathVar = Environment.GetEnvironmentVariable("PATH") ?? "";
            string[] dirs = pathVar.Split(new char[] { Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries);
            foreach (string dir in dirs)
            {
                string clean = dir.Trim('"');
                if (clean.Length == 0) continue;
                try
                {
                    string cand = Path.Combine(clean, "pythonw.exe");
                    if (File.Exists(cand)) return cand;
                }
                catch { }
            }

            // 2) common install locations (python.org, Microsoft Store, WindowsApps)
            string local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python");
            string pf = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Python");
            string pfx86 = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Python");
            string winapps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "WindowsApps");
            foreach (string root in new string[] { local, pf, pfx86, winapps })
            {
                try
                {
                    if (!Directory.Exists(root)) continue;
                    string[] files = Directory.GetFiles(root, "pythonw.exe", SearchOption.AllDirectories);
                    if (files.Length > 0) return files[0];
                }
                catch { }
            }
            return null;
        }
    }
}
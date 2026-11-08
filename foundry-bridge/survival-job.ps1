# Test helper (Windows): runs a parent process inside a Windows Job Object with KILL_ON_JOB_CLOSE, waits for the parent to exit, then closes the job
# (this is what a host that "kills its children on exit" does). Used by survival.test.mjs to prove which launch modes outlive their parent.
#   powershell -File survival-job.ps1 -Node node.exe -Script parent.mjs -ScriptArgs <args...>
param([Parameter(Mandatory)][string]$Node, [Parameter(Mandatory)][string]$Script, [string[]]$ScriptArgs = @())
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class VbJob {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr CreateJobObject(IntPtr a, string n);
  [DllImport("kernel32.dll")] public static extern bool SetInformationJobObject(IntPtr j, int cls, IntPtr info, uint len);
  [DllImport("kernel32.dll")] public static extern bool AssignProcessToJobObject(IntPtr j, IntPtr p);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  public static IntPtr Make() {
    IntPtr j = CreateJobObject(IntPtr.Zero, null);
    int len = IntPtr.Size == 8 ? 144 : 112, flagsOff = 16;
    IntPtr buf = Marshal.AllocHGlobal(len);
    for (int i = 0; i < len; i++) Marshal.WriteByte(buf, i, 0);
    Marshal.WriteInt32(buf, flagsOff, 0x2000);   // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (!SetInformationJobObject(j, 9, buf, (uint)len)) throw new Exception("SetInformationJobObject failed");
    return j;
  }
}
"@
$job = [VbJob]::Make()
$p = Start-Process -FilePath $Node -ArgumentList (@($Script) + $ScriptArgs) -PassThru -WindowStyle Hidden
if (-not [VbJob]::AssignProcessToJobObject($job, $p.Handle)) { Write-Output "ASSIGN-FAILED"; exit 2 }
[void]$p.WaitForExit(90000)
Write-Output "parent-exited $($p.ExitCode)"
[void][VbJob]::CloseHandle($job)     # kills everything still in the job
Start-Sleep -Milliseconds 1500
Write-Output "job-closed"
